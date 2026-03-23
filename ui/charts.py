"""
ui/charts.py
Plotly figure builders — pure chart logic, no Streamlit calls.
"""

import plotly.graph_objects as go
import pandas as pd


def oi_distribution_chart(
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
    current_price: float,
    max_pain: float,
    expiry_date: str,
) -> go.Figure:
    """OI distribution bar chart with current price and max pain annotations."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=calls_df["strike"],
        y=calls_df["openInterest"],
        name="Calls (壓力)",
        marker_color="rgba(0, 200, 100, 0.6)",
    ))
    fig.add_trace(go.Bar(
        x=puts_df["strike"],
        y=puts_df["openInterest"],
        name="Puts (支撐)",
        marker_color="rgba(255, 80, 80, 0.6)",
    ))

    fig.add_vline(
        x=current_price,
        line_width=2,
        line_dash="dash",
        line_color="#FFD700",
        annotation_text=f"現價 ${current_price:.2f}",
        annotation_font_color="#FFD700",
    )
    if max_pain > 0:
        fig.add_vline(
            x=max_pain,
            line_width=2,
            line_dash="dot",
            line_color="#FF4444",
            annotation_text=f"Max Pain ${max_pain:.2f}",
            annotation_font_color="#FF4444",
            annotation_position="top left",
        )

    fig.update_layout(
        barmode="overlay",
        title=f"Open Interest Distribution — {expiry_date}",
        xaxis_title="Strike Price",
        yaxis_title="Open Interest",
        paper_bgcolor="#0e0e0e",
        plot_bgcolor="#1a1a1a",
        font_color="#cccccc",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def volatility_smile_chart(
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
    current_price: float,
    expiry_date: str,
) -> go.Figure:
    """Implied Volatility vs Strike (volatility smile / skew)."""
    calls_sorted = calls_df.sort_values("strike")
    puts_sorted = puts_df.sort_values("strike")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=calls_sorted["strike"],
        y=calls_sorted["impliedVolatility"] * 100,
        mode="lines+markers",
        name="Calls IV",
        line=dict(color="#00ff88", width=2),
        marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=puts_sorted["strike"],
        y=puts_sorted["impliedVolatility"] * 100,
        mode="lines+markers",
        name="Puts IV",
        line=dict(color="#ff6666", width=2),
        marker=dict(size=5),
    ))

    fig.add_vline(
        x=current_price,
        line_width=2,
        line_dash="dash",
        line_color="#FFD700",
        annotation_text=f"現價 ${current_price:.2f}",
        annotation_font_color="#FFD700",
    )
    fig.update_layout(
        title=f"Volatility Smile — {expiry_date}",
        xaxis_title="Strike Price",
        yaxis_title="Implied Volatility (%)",
        paper_bgcolor="#0e0e0e",
        plot_bgcolor="#1a1a1a",
        font_color="#cccccc",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def bs_comparison_chart(
    df: pd.DataFrame,
    option_type: str,
    current_price: float,
) -> go.Figure:
    """Market price vs Black-Scholes theoretical price across strikes."""
    df_sorted = df.sort_values("strike")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted["strike"],
        y=df_sorted["lastPrice"],
        mode="lines+markers",
        name="市場價格",
        line=dict(color="#FFD700", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=df_sorted["strike"],
        y=df_sorted["BS_Price"],
        mode="lines+markers",
        name="BS 理論價格",
        line=dict(color="#00aaff", width=2, dash="dash"),
    ))

    fig.add_vline(
        x=current_price,
        line_width=1,
        line_dash="dot",
        line_color="#aaaaaa",
        annotation_text="現價",
        annotation_font_color="#aaaaaa",
    )
    label = "Call" if option_type == "call" else "Put"
    fig.update_layout(
        title=f"{label} — 市場價 vs Black-Scholes 理論價",
        xaxis_title="Strike Price",
        yaxis_title="Option Price (USD)",
        paper_bgcolor="#0e0e0e",
        plot_bgcolor="#1a1a1a",
        font_color="#cccccc",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig
