# Polymarket API Authentication Setup

## Overview

Some Polymarket API endpoints require authentication to access markets and place trades. This guide will help you set up authentication.

## Step 1: Get Your API Credentials

1. Go to https://polymarket.com/settings/api
2. Create an API key if you don't have one
3. Copy your:
   - API Key
   - Private Key (if available)
   - Wallet Address

## Step 2: Create .env File

1. Copy the example file:
   ```bash
   cp env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```
   POLYMARKET_API_KEY=your_actual_api_key_here
   POLYMARKET_PRIVATE_KEY=your_actual_private_key_here
   POLYMARKET_WALLET_ADDRESS=your_wallet_address_here
   ```

3. **Important:** Never commit your `.env` file to git! It's already in `.gitignore`.

## Step 3: Verify Authentication

Run the bot and check the logs. You should see:
```
✅ Polymarket API authentication configured
```

If you see:
```
⚠️ No Polymarket API key found - some endpoints may require authentication
```

Then your `.env` file is not being loaded correctly. Check:
- File is named exactly `.env` (not `env` or `.env.txt`)
- File is in the project root directory
- Credentials are set correctly (no extra spaces or quotes)

## Authentication Methods

The bot uses the following authentication methods:

### 1. Bearer Token (Primary)
- Uses `Authorization: Bearer {API_KEY}` header
- Used for most read operations

### 2. API Key Header
- Uses `X-API-Key: {API_KEY}` header
- Fallback method for some endpoints

### 3. Private Key Signing (Future)
- For placing trades, you may need to sign requests with your private key
- This will be implemented when live trading is enabled

## Troubleshooting

### 401 Unauthorized Errors
- Check that your API key is correct
- Verify the key hasn't expired
- Make sure there are no extra spaces in `.env` file

### 403 Forbidden Errors
- Your API key may not have the required permissions
- Check your API key settings on Polymarket

### Markets Not Found
- Some endpoints may require authentication even for public data
- Make sure your `.env` file is set up correctly
- Try accessing the Polymarket website to verify markets are available

## Security Notes

- **Never share your API keys**
- **Never commit `.env` to version control**
- **Rotate keys regularly**
- **Use different keys for development and production**

## Next Steps

Once authentication is set up:
1. Test the connection: `python test_connection.py`
2. Run the bot: `python main.py`
3. Check logs for authentication status

