"""Rich terminal dashboard for the Polymarket trading bot."""

import time
from datetime import datetime
from collections import deque

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress_bar import ProgressBar
from rich import box

console = Console()


class Dashboard:
    """Live terminal UI that displays bot state each tick."""

    def __init__(self, config):
        self.config = config
        self.tick_count: int = 0
        self.markets_scanned: int = 0
        self.signals_found: int = 0
        self.trades_executed: int = 0
        self.trades_rejected: int = 0
        self.api_calls_saved: int = 0
        self.last_tick_time: float = 0.0
        self.start_time: float = time.time()
        self.log_entries: deque[tuple[str, str, str]] = deque(maxlen=15)
        self._live: Live | None = None

    # ── Logging ────────────────────────────────────────────────────

    def log(self, level: str, message: str):
        """Add an entry to the activity log."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_entries.append((ts, level, message))

    def log_signal(self, action: str, token_id: str, price: float, reason: str):
        self.signals_found += 1
        tag = "[green]BUY[/green]" if action == "BUY" else "[red]SELL[/red]"
        self.log("SIGNAL", f"{tag} {token_id[:10]}.. @ ${price:.4f} - {reason[:45]}")

    def log_trade(self, action: str, token_id: str, price: float, size: float):
        self.trades_executed += 1
        tag = "[bold green]BUY[/bold green]" if action == "BUY" else "[bold red]SELL[/bold red]"
        self.log("TRADE", f"{tag} {size:.1f} x {token_id[:10]}.. @ ${price:.4f}")

    def log_rejected(self, reason: str):
        self.trades_rejected += 1
        self.log("RISK", f"[yellow]Rejected:[/yellow] {reason[:55]}")

    def log_stop_loss(self, token_id: str, loss_pct: float):
        self.log("RISK", f"[bold red]STOP LOSS[/bold red] {token_id[:10]}.. (-{loss_pct:.1f}%)")

    def log_take_profit(self, token_id: str, gain_pct: float):
        self.log("RISK", f"[bold green]TAKE PROFIT[/bold green] {token_id[:10]}.. (+{gain_pct:.1f}%)")

    def log_info(self, message: str):
        self.log("INFO", message)

    def log_error(self, message: str):
        self.log("ERROR", f"[red]{message}[/red]")

    # ── Rendering ──────────────────────────────────────────────────

    def _build_header(self) -> Panel:
        uptime = int(time.time() - self.start_time)
        h, m, s = uptime // 3600, (uptime % 3600) // 60, uptime % 60

        mode = "[bold red]LIVE[/bold red]" if not self.config.dry_run else "[bold yellow]DRY RUN[/bold yellow]"

        grid = Table.grid(padding=(0, 3))
        grid.add_row(
            f"[bold cyan]POLYMARKET BOT[/bold cyan]  {mode}",
            f"Capital: [bold]${self.config.max_position_size:.0f}[/bold]",
            f"Order: [bold]${self.config.order_size:.0f}[/bold]",
            f"Tick #{self.tick_count}",
            f"Uptime: {h:02d}:{m:02d}:{s:02d}",
        )
        return Panel(grid, style="bright_blue", box=box.HEAVY)

    def _build_positions_table(self, positions: dict, get_price_fn) -> Panel:
        table = Table(box=box.SIMPLE_HEAVY, expand=True, show_edge=False)
        table.add_column("Mercado", style="cyan", max_width=35, no_wrap=True)
        table.add_column("Lado", justify="center", width=6)
        table.add_column("Cant.", justify="right", width=7)
        table.add_column("Entrada", justify="right", width=9)
        table.add_column("Actual", justify="right", width=9)
        table.add_column("P&L", justify="right", width=10)
        table.add_column("P&L %", justify="right", width=8)

        total_pnl = 0.0
        if not positions:
            table.add_row("[dim]Sin posiciones abiertas[/dim]", "", "", "", "", "", "")
        else:
            for tid, pos in positions.items():
                try:
                    current = get_price_fn(tid)
                except Exception:
                    current = pos.entry_price

                if pos.side == "BUY":
                    pnl = (current - pos.entry_price) * pos.size
                    pnl_pct = ((current - pos.entry_price) / pos.entry_price) * 100 if pos.entry_price else 0
                else:
                    pnl = (pos.entry_price - current) * pos.size
                    pnl_pct = ((pos.entry_price - current) / pos.entry_price) * 100 if pos.entry_price else 0

                total_pnl += pnl
                pnl_color = "green" if pnl >= 0 else "red"
                side_display = "[green]LONG[/green]" if pos.side == "BUY" else "[red]SHORT[/red]"

                name = pos.market_name[:33] if pos.market_name else tid[:33]
                table.add_row(
                    name,
                    side_display,
                    f"{pos.size:.1f}",
                    f"${pos.entry_price:.4f}",
                    f"${current:.4f}",
                    f"[{pnl_color}]${pnl:+.2f}[/{pnl_color}]",
                    f"[{pnl_color}]{pnl_pct:+.1f}%[/{pnl_color}]",
                )

        pnl_style = "green" if total_pnl >= 0 else "red"
        title = f"Posiciones ({len(positions)})  |  P&L Total: [{pnl_style}]${total_pnl:+.2f}[/{pnl_style}]"
        return Panel(table, title=title, border_style="green" if total_pnl >= 0 else "red")

    def _build_stats(self) -> Panel:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="bold")
        table.add_column()

        table.add_row("Mercados escaneados:", f"[cyan]{self.markets_scanned}[/cyan]")
        table.add_row("Senales detectadas:", f"[yellow]{self.signals_found}[/yellow]")
        table.add_row("Trades ejecutados:", f"[green]{self.trades_executed}[/green]")
        table.add_row("Trades rechazados:", f"[red]{self.trades_rejected}[/red]")
        table.add_row("API calls ahorradas:", f"[magenta]{self.api_calls_saved}[/magenta]")

        tick_ms = self.last_tick_time * 1000
        speed_color = "green" if tick_ms < 5000 else "yellow" if tick_ms < 15000 else "red"
        table.add_row("Tiempo ultimo tick:", f"[{speed_color}]{tick_ms:.0f}ms[/{speed_color}]")

        return Panel(table, title="Estadisticas", border_style="blue")

    def _build_exposure_bar(self, total_exposure: float) -> Panel:
        max_pos = self.config.max_position_size
        ratio = min(total_exposure / max_pos, 1.0) if max_pos > 0 else 0
        pct = ratio * 100

        bar_color = "green" if pct < 50 else "yellow" if pct < 80 else "red"
        available = max_pos - total_exposure

        bar = Table.grid(padding=(0, 1), expand=True)
        bar.add_column(ratio=8)
        bar.add_column(ratio=2, justify="right")

        progress = ProgressBar(total=100, completed=pct, width=None)
        bar.add_row(
            progress,
            Text(f"${total_exposure:.2f} / ${max_pos:.2f}", style=bar_color),
        )

        return Panel(
            bar,
            title=f"Exposicion  |  Disponible: [bold]${available:.2f}[/bold]",
            border_style=bar_color,
        )

    def _build_activity_log(self) -> Panel:
        if not self.log_entries:
            content = Text("Esperando primer tick...", style="dim")
        else:
            lines = []
            for ts, level, msg in self.log_entries:
                level_colors = {
                    "SIGNAL": "yellow",
                    "TRADE": "green",
                    "RISK": "red",
                    "INFO": "blue",
                    "ERROR": "red",
                }
                color = level_colors.get(level, "white")
                lines.append(f"[dim]{ts}[/dim] [{color}]{level:6s}[/{color}] {msg}")
            content = Text.from_markup("\n".join(lines))

        return Panel(content, title="Actividad Reciente", border_style="yellow")

    def render(self, risk_manager, get_price_fn) -> Layout:
        """Build the full dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="log", size=min(len(self.log_entries) + 3, 18)),
        )

        layout["body"].split_row(
            Layout(name="left", ratio=7),
            Layout(name="right", ratio=3),
        )

        layout["left"].split_column(
            Layout(name="positions"),
            Layout(name="exposure", size=4),
        )

        layout["right"].split_column(
            Layout(name="stats"),
        )

        layout["header"].update(self._build_header())
        layout["positions"].update(
            self._build_positions_table(risk_manager.positions, get_price_fn)
        )
        layout["exposure"].update(self._build_exposure_bar(risk_manager.total_exposure))
        layout["stats"].update(self._build_stats())
        layout["log"].update(self._build_activity_log())

        return layout

    # ── Live display control ───────────────────────────────────────

    def start(self) -> Live:
        self._live = Live(
            console=console,
            refresh_per_second=1,
            screen=False,
        )
        self._live.start()
        return self._live

    def update(self, risk_manager, get_price_fn):
        """Re-render the dashboard."""
        if self._live:
            self._live.update(self.render(risk_manager, get_price_fn))

    def stop(self):
        if self._live:
            self._live.stop()
            self._live = None
