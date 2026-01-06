"""
Terminal Dashboard UI
Beautiful multi-pane display showing Binance price, market info, and trades
"""

import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Fallback if rich not available
    Console = None
    Panel = None
    Layout = None
    Live = None
    Table = None
    Text = None
    box = None

if RICH_AVAILABLE:
    console = Console()


@dataclass
class DashboardData:
    """Data structure for dashboard updates"""
    # Binance data
    btc_price: Optional[float] = None
    btc_change_24h: Optional[float] = None
    last_price_update: Optional[float] = None
    
    # Market data
    market_question: Optional[str] = None
    market_condition_id: Optional[str] = None
    market_time_remaining: Optional[float] = None
    market_time_elapsed: Optional[float] = None
    market_accepting_orders: bool = False
    market_active: bool = False
    
    # Orderbook data
    up_token_id: Optional[str] = None
    down_token_id: Optional[str] = None
    up_best_bid: Optional[float] = None
    up_best_ask: Optional[float] = None
    up_spread: Optional[float] = None
    down_best_bid: Optional[float] = None
    down_best_ask: Optional[float] = None
    down_spread: Optional[float] = None
    
    # Trading data
    recent_trades: List[Dict] = None
    open_positions: List[Dict] = None
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    bankroll: float = 200.0
    
    # Signal data
    last_signal: Optional[str] = None
    last_signal_time: Optional[float] = None
    
    def __post_init__(self):
        if self.recent_trades is None:
            self.recent_trades = []
        if self.open_positions is None:
            self.open_positions = []


class Dashboard:
    """Terminal dashboard with 3 panes"""
    
    def __init__(self):
        if not RICH_AVAILABLE:
            raise ImportError("rich library is required for dashboard. Install with: pip install rich")
        self.data = DashboardData()
        self.layout = Layout()
        self.setup_layout()
    
    def setup_layout(self):
        """Setup the 3-pane layout"""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body")
        )
        
        self.layout["body"].split_row(
            Layout(name="binance", ratio=1),
            Layout(name="market", ratio=1),
            Layout(name="trades", ratio=1)
        )
    
    def create_binance_panel(self) -> Panel:
        """Create Binance price panel"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        
        if self.data.btc_price:
            price_text = Text(f"${self.data.btc_price:,.2f}", style="bold green" if self.data.btc_price else "white")
            table.add_row("BTC/USDT", price_text)
            
            if self.data.btc_change_24h is not None:
                change_style = "green" if self.data.btc_change_24h >= 0 else "red"
                change_symbol = "▲" if self.data.btc_change_24h >= 0 else "▼"
                table.add_row("24h Change", Text(f"{change_symbol} {abs(self.data.btc_change_24h):.2f}%", style=change_style))
            
            if self.data.last_price_update:
                update_age = time.time() - self.data.last_price_update
                if update_age < 1:
                    status = Text("● LIVE", style="green")
                elif update_age < 5:
                    status = Text("● UPDATING", style="yellow")
                else:
                    status = Text("● STALE", style="red")
                table.add_row("Status", status)
        else:
            table.add_row("BTC/USDT", Text("Waiting...", style="dim"))
        
        return Panel(
            table,
            title="[bold cyan]📈 Binance Price[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        )
    
    def create_market_panel(self) -> Panel:
        """Create market info panel"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        
        if self.data.market_question:
            # Market question (truncated)
            question = self.data.market_question[:60] + "..." if len(self.data.market_question) > 60 else self.data.market_question
            table.add_row("Market", Text(question, style="bold"))
            
            # Time info
            if self.data.market_time_remaining is not None:
                remaining = self.data.market_time_remaining
                elapsed = self.data.market_time_elapsed or 0
                time_style = "green" if remaining > 5 else "yellow" if remaining > 2 else "red"
                table.add_row("Time", Text(f"{remaining:.1f}m remaining ({elapsed:.1f}m elapsed)", style=time_style))
            
            # Status
            status_parts = []
            if self.data.market_active:
                status_parts.append(Text("● Active", style="green"))
            if self.data.market_accepting_orders:
                status_parts.append(Text("● Accepting Orders", style="green"))
            if status_parts:
                table.add_row("Status", Text(" ").join(status_parts))
            
            # Orderbook - UP token
            if self.data.up_best_bid and self.data.up_best_ask:
                table.add_row("", "")  # Spacer
                table.add_row(Text("UP Token", style="bold yellow"), "")
                table.add_row("  Bid", Text(f"${self.data.up_best_bid:.3f}", style="green"))
                table.add_row("  Ask", Text(f"${self.data.up_best_ask:.3f}", style="red"))
                if self.data.up_spread is not None:
                    table.add_row("  Spread", Text(f"${self.data.up_spread:.3f}", style="dim"))
            
            # Orderbook - DOWN token
            if self.data.down_best_bid and self.data.down_best_ask:
                table.add_row("", "")  # Spacer
                table.add_row(Text("DOWN Token", style="bold yellow"), "")
                table.add_row("  Bid", Text(f"${self.data.down_best_bid:.3f}", style="green"))
                table.add_row("  Ask", Text(f"${self.data.down_best_ask:.3f}", style="red"))
                if self.data.down_spread is not None:
                    table.add_row("  Spread", Text(f"${self.data.down_spread:.3f}", style="dim"))
        else:
            table.add_row("Market", Text("No active market", style="dim"))
        
        return Panel(
            table,
            title="[bold yellow]📊 Market & Orderbook[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED
        )
    
    def create_trades_panel(self) -> Panel:
        """Create trades and positions panel"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        
        # Stats
        table.add_row(Text("Stats", style="bold"), "")
        table.add_row("Total Trades", Text(str(self.data.total_trades), style="bold"))
        table.add_row("Wins", Text(str(self.data.wins), style="green"))
        table.add_row("Losses", Text(str(self.data.losses), style="red"))
        table.add_row("Win Rate", Text(f"{self.data.win_rate:.1f}%", style="bold"))
        table.add_row("Total P&L", Text(f"${self.data.total_pnl:+.2f}", 
                                       style="green" if self.data.total_pnl >= 0 else "red"))
        table.add_row("Bankroll", Text(f"${self.data.bankroll:.2f}", style="bold cyan"))
        
        # Recent signal
        if self.data.last_signal:
            signal_age = time.time() - (self.data.last_signal_time or 0) if self.data.last_signal_time else 0
            if signal_age < 30:
                table.add_row("", "")  # Spacer
                table.add_row(Text("Last Signal", style="bold"), "")
                table.add_row("", Text(self.data.last_signal, style="yellow"))
        
        # Recent trades
        if self.data.recent_trades:
            table.add_row("", "")  # Spacer
            table.add_row(Text("Recent Trades", style="bold"), "")
            for trade in self.data.recent_trades[-5:]:  # Last 5 trades
                direction = trade.get('direction', 'N/A')
                profit = trade.get('profit', 0)
                status = "✅" if trade.get('won') else "❌"
                profit_text = Text(f"{status} {direction} ${profit:+.2f}", 
                                  style="green" if profit > 0 else "red")
                table.add_row(f"#{trade.get('id', '?')}", profit_text)
        
        # Open positions
        if self.data.open_positions:
            table.add_row("", "")  # Spacer
            table.add_row(Text("Open Positions", style="bold"), "")
            for pos in self.data.open_positions:
                direction = pos.get('direction', 'N/A')
                size = pos.get('size', 0)
                table.add_row(f"#{pos.get('id', '?')}", Text(f"{direction} ${size:.2f}", style="cyan"))
        
        return Panel(
            table,
            title="[bold magenta]💰 Trades & Positions[/bold magenta]",
            border_style="magenta",
            box=box.ROUNDED
        )
    
    def create_header(self) -> Panel:
        """Create header panel"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = "📝 PAPER TRADING" if True else "💰 LIVE TRADING"  # TODO: Get from config
        
        header_text = Text()
        header_text.append("🤖 POLYMARKET LATENCY ARBITRAGE BOT", style="bold white")
        header_text.append(" | ")
        header_text.append(mode, style="bold yellow")
        header_text.append(" | ")
        header_text.append(now, style="dim")
        
        return Panel(
            header_text,
            border_style="blue",
            box=box.ROUNDED
        )
    
    def render(self) -> Layout:
        """Render the complete dashboard"""
        self.layout["header"].update(self.create_header())
        self.layout["binance"].update(self.create_binance_panel())
        self.layout["market"].update(self.create_market_panel())
        self.layout["trades"].update(self.create_trades_panel())
        return self.layout
    
    def render_live(self):
        """Render the dashboard (for use with Live context manager)"""
        return self.render()

