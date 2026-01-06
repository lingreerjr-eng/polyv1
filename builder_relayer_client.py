"""
Polymarket Builder API Relayer Client
Handles gasless merge and redeem operations using Builder API and Relayer
"""

import time
import hmac
import hashlib
import base64
import json
import logging
from typing import Optional, Dict, List, Any
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import requests

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BuilderRelayerClient:
    """
    Client for interacting with Polymarket Builder API and Relayer
    Enables gasless merge and redeem operations
    """

    def __init__(self):
        """Initialize the Builder Relayer Client"""
        # Validate Builder API credentials
        if not all([config.POLY_BUILDER_API_KEY, config.POLY_BUILDER_SECRET, config.POLY_BUILDER_PASSPHRASE]):
            logger.warning("⚠️ Builder API credentials not configured - merge/redeem will be disabled")
            self.enabled = False
            return

        # Validate proxy wallet
        if not config.PROXY_WALLET_PRIVATE_KEY:
            logger.warning("⚠️ Proxy wallet private key not configured - merge/redeem will be disabled")
            self.enabled = False
            return

        self.enabled = True
        self.api_key = config.POLY_BUILDER_API_KEY
        self.secret = config.POLY_BUILDER_SECRET
        self.passphrase = config.POLY_BUILDER_PASSPHRASE
        self.relayer_url = config.POLYMARKET_RELAYER

        # Initialize Web3 for Polygon
        self.w3 = Web3(Web3.HTTPProvider(config.POLYGON_RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Polygon RPC")

        # Initialize account from private key
        self.account = Account.from_key(config.PROXY_WALLET_PRIVATE_KEY)
        self.wallet_address = self.account.address

        logger.info(f"✅ Builder Relayer Client initialized")
        logger.info(f"   Wallet: {self.wallet_address}")

    def _generate_builder_headers(self, method: str, path: str, body: str = '') -> Dict[str, str]:
        """
        Generate Builder API authentication headers using HMAC-SHA256

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            body: Request body as string

        Returns:
            Dictionary of headers for authenticated requests
        """
        timestamp = str(int(time.time() * 1000))  # Milliseconds
        message = f'{timestamp}{method.upper()}{path}{body}'
        
        # Decode base64 secret
        hmac_key = base64.b64decode(self.secret)
        
        # Generate HMAC-SHA256 signature
        signature = hmac.new(hmac_key, message.encode('utf-8'), hashlib.sha256).digest()
        signature_b64 = base64.b64encode(signature).decode('utf-8')

        headers = {
            'POLY-API-KEY': self.api_key,
            'POLY-SIGNATURE': signature_b64,
            'POLY-TIMESTAMP': timestamp,
            'POLY-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }

        return headers

    def _encode_redeem_positions(self, condition_id: str, index_sets: List[int], amounts: List[int]) -> str:
        """
        Encode redeemPositions function call for CTF contract

        Args:
            condition_id: The condition ID (bytes32)
            index_sets: List of index sets (outcome slots) to redeem
            amounts: List of amounts to redeem for each index set

        Returns:
            Encoded function data (hex string)
        """
        # CTF redeemPositions ABI
        ctf_abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "collateralToken", "type": "address"},
                    {"name": "parentCollectionId", "type": "bytes32"},
                    {"name": "conditionId", "type": "bytes32"},
                    {"name": "indexSets", "type": "uint256[]"},
                    {"name": "amounts", "type": "uint256[]"}
                ],
                "name": "redeemPositions",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

        # Create contract instance
        ctf_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.CTF_CONTRACT_ADDRESS),
            abi=ctf_abi
        )

        # Prepare parameters
        collateral_token = Web3.to_checksum_address(config.USDC_E_ADDRESS)
        parent_collection_id = '0x' + '0' * 64  # Null parent collection
        condition_id_bytes = Web3.to_bytes(hexstr=condition_id) if not condition_id.startswith('0x') else Web3.to_bytes(hexstr=condition_id)

        # Encode function call
        function = ctf_contract.functions.redeemPositions(
            collateral_token,
            parent_collection_id,
            condition_id_bytes,
            index_sets,
            amounts
        )

        # Build transaction to get encoded data
        tx = function.build_transaction({'from': self.wallet_address})
        return tx['data']

    def _encode_merge_positions(self, condition_id: str, index_sets: List[int], amounts: List[int]) -> str:
        """
        Encode mergePositions function call for CTF contract
        Merges YES and NO tokens back into collateral

        Args:
            condition_id: The condition ID (bytes32)
            index_sets: List of index sets [1, 2] for YES and NO
            amounts: List of amounts to merge for each index set

        Returns:
            Encoded function data (hex string)
        """
        # CTF mergePositions ABI (similar to redeemPositions)
        ctf_abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "collateralToken", "type": "address"},
                    {"name": "parentCollectionId", "type": "bytes32"},
                    {"name": "conditionId", "type": "bytes32"},
                    {"name": "indexSets", "type": "uint256[]"},
                    {"name": "amounts", "type": "uint256[]"}
                ],
                "name": "mergePositions",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

        # Create contract instance
        ctf_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.CTF_CONTRACT_ADDRESS),
            abi=ctf_abi
        )

        # Prepare parameters
        collateral_token = Web3.to_checksum_address(config.USDC_E_ADDRESS)
        parent_collection_id = '0x' + '0' * 64  # Null parent collection
        # Ensure condition_id is properly formatted as bytes32
        if condition_id.startswith('0x'):
            condition_id_bytes = Web3.to_bytes(hexstr=condition_id)
        else:
            condition_id_bytes = Web3.to_bytes(hexstr='0x' + condition_id)

        # Encode function call
        function = ctf_contract.functions.mergePositions(
            collateral_token,
            parent_collection_id,
            condition_id_bytes,
            index_sets,
            amounts
        )

        # Build transaction to get encoded data
        tx = function.build_transaction({'from': self.wallet_address})
        return tx['data']

    def _send_relayer_transaction(self, to: str, data: str, value: int = 0) -> Optional[Dict[str, Any]]:
        """
        Send a transaction through the Polymarket relayer (gasless)

        Args:
            to: Contract address to call
            data: Encoded function data
            value: ETH/MATIC value to send (usually 0)

        Returns:
            Transaction response or None if failed
        """
        if not self.enabled:
            logger.error("❌ Builder Relayer Client not enabled")
            return None

        try:
            # Get nonce
            nonce = self.w3.eth.get_transaction_count(self.wallet_address)

            # Build transaction
            transaction = {
                'to': Web3.to_checksum_address(to),
                'data': data,
                'value': value,
                'gas': 500000,  # Sufficient gas for CTF operations
                'gasPrice': self.w3.eth.gas_price,
                'nonce': nonce,
                'chainId': config.POLYGON_CHAIN_ID
            }

            # Sign transaction
            signed_txn = self.account.sign_transaction(transaction)
            signed_tx_hex = signed_txn.rawTransaction.hex()

            # Prepare relayer request
            # The relayer expects the signed transaction in the request
            relayer_payload = {
                'signedTx': signed_tx_hex
            }

            # Generate Builder API headers
            path = '/relay'
            body = json.dumps(relayer_payload)
            headers = self._generate_builder_headers('POST', path, body)

            # Send to relayer
            response = requests.post(
                f"{self.relayer_url}{path}",
                json=relayer_payload,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                tx_hash = result.get('txHash') or result.get('hash') or result.get('transactionHash')
                logger.info(f"✅ Relayer transaction submitted: {tx_hash}")
                return result
            else:
                logger.error(f"❌ Relayer request failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ Error sending relayer transaction: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def redeem_positions(self, condition_id: str, index_set: int, amount: int) -> Optional[Dict[str, Any]]:
        """
        Redeem winning outcome tokens for collateral (USDC.e)

        Args:
            condition_id: The condition ID of the resolved market
            index_set: Index set for the outcome (1 = YES, 2 = NO)
            amount: Amount of tokens to redeem (in wei, 6 decimals for USDC.e)

        Returns:
            Transaction result or None if failed
        """
        if not self.enabled:
            logger.warning("⚠️ Builder Relayer Client not enabled - cannot redeem")
            return None

        logger.info(f"🔄 Redeeming positions: condition={condition_id}, index_set={index_set}, amount={amount}")

        # Encode redeem function
        data = self._encode_redeem_positions(
            condition_id=condition_id,
            index_sets=[index_set],
            amounts=[amount]
        )

        # Send via relayer
        return self._send_relayer_transaction(
            to=config.CTF_CONTRACT_ADDRESS,
            data=data,
            value=0
        )

    def merge_positions(self, condition_id: str, yes_amount: int, no_amount: int) -> Optional[Dict[str, Any]]:
        """
        Merge YES and NO tokens back into collateral (USDC.e)
        Useful when you have both YES and NO tokens and want to get collateral back

        Args:
            condition_id: The condition ID of the market
            yes_amount: Amount of YES tokens to merge (in wei, 6 decimals)
            no_amount: Amount of NO tokens to merge (in wei, 6 decimals)

        Returns:
            Transaction result or None if failed
        """
        if not self.enabled:
            logger.warning("⚠️ Builder Relayer Client not enabled - cannot merge")
            return None

        logger.info(f"🔄 Merging positions: condition={condition_id}, yes={yes_amount}, no={no_amount}")

        # Encode merge function
        data = self._encode_merge_positions(
            condition_id=condition_id,
            index_sets=[1, 2],  # YES = 1, NO = 2
            amounts=[yes_amount, no_amount]
        )

        # Send via relayer
        return self._send_relayer_transaction(
            to=config.CTF_CONTRACT_ADDRESS,
            data=data,
            value=0
        )

    def check_wallet_balance(self) -> Dict[str, float]:
        """
        Check wallet balances (MATIC and USDC.e)

        Returns:
            Dictionary with MATIC and USDC.e balances
        """
        if not self.enabled:
            return {'matic': 0.0, 'usdc_e': 0.0}

        try:
            # Get MATIC balance
            matic_balance_wei = self.w3.eth.get_balance(self.wallet_address)
            matic_balance = self.w3.from_wei(matic_balance_wei, 'ether')

            # Get USDC.e balance (ERC20)
            usdc_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                }
            ]

            usdc_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.USDC_E_ADDRESS),
                abi=usdc_abi
            )

            usdc_balance_raw = usdc_contract.functions.balanceOf(self.wallet_address).call()
            decimals = usdc_contract.functions.decimals().call()
            usdc_balance = usdc_balance_raw / (10 ** decimals)

            return {
                'matic': float(matic_balance),
                'usdc_e': float(usdc_balance)
            }

        except Exception as e:
            logger.error(f"❌ Error checking wallet balance: {e}")
            return {'matic': 0.0, 'usdc_e': 0.0}

