import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators, score_technical
from fundamentals.ratios import safe_float

st.title("Portfolio & Risk")
st.caption("Track positions, compute risk metrics, and analyze portfolio concentration")

PORTFOLIO_KEY = "portfolio_positions"

if PORTFOLIO_KEY not in st.session_state:
    st.session_state[PORTFOLIO_KEY] = []

st.sidebar.header("Portfolio Manager")
st.sidebar.caption("Add or remove positions")

COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "ITC": "ITC.NS",
    "Wipro": "WIPRO.NS",
    "HCL Technologies": "HCLTECH.NS",
}

with st.sidebar.form("add_position"):
    pos_company = st.selectbox("Add Position", list(COMPANIES.keys()))
    pos_symbol = COMPANIES[pos_company]
    pos_shares = st.number_input("Shares", min_value=1, value=100, step=10)
    pos_price = st.number_input("Entry Price (₹)", min_value=0.0, value=0.0, step=0.01)
    pos_risk_pct = st.slider("Risk per Trade (%)", min_value=0.1, max_value=10.0, value=2.0, step=0.1)
    pos_added = st.form_submit_button("Add Position")

    if pos_added:
        existing = [p for p in st.session_state[PORTFOLIO_KEY] if p["symbol"] == pos_symbol]
        if existing:
            st.warning(f"{pos_company} already in portfolio. Use the remove button to delete it first.")
        else:
            st.session_state[PORTFOLIO_KEY].append({
                "company": pos_company,
                "symbol": pos_symbol,
                "shares": pos_shares,
                "entry_price": pos_price,
                "risk_pct": pos_risk_pct,
            })
            st.success(f"Added {pos_company} ({pos_symbol})")

st.sidebar.divider()
if st.sidebar.button("Clear All Positions"):
    st.session_state[PORTFOLIO_KEY] = []
    st.rerun()


def main():
    positions = st.session_state[PORTFOLIO_KEY]

    if not positions:
        st.info("No positions in portfolio. Add positions using the sidebar form.")
        return

    st.subheader("Current Positions")
    pos_rows = []
    for i, pos in enumerate(positions):
        pos_rows.append({
            "#": i + 1,
            "Company": pos["company"],
            "Symbol": pos["symbol"],
            "Shares": pos["shares"],
            "Entry Price": f"₹{pos['entry_price']:,.2f}",
            "Risk %": f"{pos.get('risk_pct', 2.0):.1f}%",
        })
    st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)

    st.divider()

    with st.spinner("Fetching live prices and computing risk metrics..."):
        portfolio_data = []
        total_market_value = 0.0
        total_cost = 0.0

        for pos in positions:
            try:
                df = fetch_prices(pos["symbol"], period="1y")
                if df.empty:
                    continue
                latest = df.iloc[-1]
                current_price = float(latest["Close"])
                market_value = pos["shares"] * current_price
                cost_basis = pos["shares"] * pos["entry_price"]
                pnl = market_value - cost_basis
                pnl_pct = (pnl / cost_basis * 100) if cost_basis != 0 else 0.0

                df_ind = compute_technical_indicators(df)
                latest_ind = df_ind.iloc[-1]
                tech = score_technical(latest_ind)

                fund = fetch_fundamentals(pos["symbol"])

                portfolio_data.append({
                    "symbol": pos["symbol"],
                    "company": pos["company"],
                    "shares": pos["shares"],
                    "entry_price": pos["entry_price"],
                    "current_price": current_price,
                    "market_value": market_value,
                    "cost_basis": cost_basis,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "technical_score": tech.get("percentage", 0),
                    "technical_signal": tech.get("signal", "N/A"),
                    "sector": fund.get("Sector") or "N/A",
                    "industry": fund.get("Industry") or "N/A",
                    "roe": fund.get("ROE"),
                    "roce": fund.get("ROCE"),
                    "debt_equity": fund.get("DebtEquity"),
                    "beta": None,
                    "risk_pct": pos.get("risk_pct", 2.0),
                })
                total_market_value += market_value
                total_cost += cost_basis
            except Exception:
                continue

    if not portfolio_data:
        st.error("No valid price data could be retrieved for any position.")
        return

    port_df = pd.DataFrame(portfolio_data)

    st.subheader("Portfolio Summary")
    total_pnl = port_df["pnl"].sum()
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost != 0 else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Market Value", f"₹{total_market_value:,.0f}")
    c2.metric("Total Cost Basis", f"₹{total_cost:,.0f}")
    c3.metric("Total P&L", f"₹{total_pnl:,.0f}", f"{total_pnl_pct:.2f}%")
    c4.metric("Number of Positions", len(portfolio_data))
    c5.metric("Avg P&L %", f"{port_df['pnl_pct'].mean():.2f}%" if not port_df["pnl_pct"].empty else "N/A")

    st.divider()

    st.subheader("Position Sizing & Risk per Trade")
    risk_rows = []
    for _, row in port_df.iterrows():
        risk_amount = total_market_value * (row["risk_pct"] / 100)
        position_size = row["shares"] * row["current_price"]
        risk_per_share = abs(row["current_price"] - row["entry_price"]) if row["current_price"] != row["entry_price"] else 0
        max_loss = risk_per_share * row["shares"]
        risk_rows.append({
            "Symbol": row["symbol"],
            "Position Size (₹)": f"₹{position_size:,.0f}",
            "Risk per Trade (%)": f"{row['risk_pct']:.1f}%",
            "Risk Amount (₹)": f"₹{risk_amount:,.0f}",
            "Risk per Share (₹)": f"₹{risk_per_share:,.2f}",
            "Max Loss (₹)": f"₹{max_loss:,.0f}",
        })
    st.dataframe(pd.DataFrame(risk_rows), use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Portfolio Allocation")
    alloc = port_df.copy()
    alloc["weight"] = alloc["market_value"] / total_market_value
    alloc_display = alloc[["company", "symbol", "market_value", "weight", "sector", "industry"]].copy()
    alloc_display["weight"] = alloc_display["weight"].apply(lambda v: f"{float(v)*100:.1f}%" if pd.notna(v) and not isinstance(v, str) else v if isinstance(v, str) else "N/A")
    alloc_display["market_value"] = alloc_display["market_value"].apply(lambda v: f"₹{float(v):,.0f}" if pd.notna(v) and not isinstance(v, str) else v if isinstance(v, str) else "N/A")
    st.dataframe(alloc_display, use_container_width=True, hide_index=True)

    fig = go.Figure()
    fig.add_trace(go.Pie(labels=alloc_display["company"], values=alloc["market_value"], hole=0.4))
    fig.update_layout(height=400, title="Portfolio Allocation by Market Value")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Sector Exposure")
    sector_exposure = port_df.groupby("sector").agg(
        Market_Value=("market_value", "sum"),
        Positions=("symbol", "count"),
    ).reset_index()
    sector_exposure["Weight"] = sector_exposure["Market_Value"] / total_market_value
    sector_exposure["Weight"] = sector_exposure["Weight"].apply(lambda v: f"{float(v)*100:.1f}%" if pd.notna(v) and not isinstance(v, str) else v if isinstance(v, str) else "N/A")
    sector_exposure["Market_Value"] = sector_exposure["Market_Value"].apply(lambda v: f"₹{float(v):,.0f}" if pd.notna(v) and not isinstance(v, str) else v if isinstance(v, str) else "N/A")
    st.dataframe(sector_exposure, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Risk Metrics")
    returns_data = {}
    for pos in positions:
        try:
            df = fetch_prices(pos["symbol"], period="1y")
            if df.empty:
                continue
            df = df.set_index("Date")["Close"].sort_index()
            if len(df) < 2:
                continue
            daily_ret = df.pct_change().dropna()
            returns_data[pos["symbol"]] = daily_ret
        except Exception:
            continue

    if returns_data:
        ret_df = pd.DataFrame(returns_data).dropna()

        if not ret_df.empty:
            st.markdown("**Individual Position Risk**")
            risk_rows = []
            for col in ret_df.columns:
                vol = ret_df[col].std() * np.sqrt(252)
                mean_ret = ret_df[col].mean() * 252
                sharpe = (mean_ret - 0.05) / vol if vol != 0 else 0
                max_dd = (ret_df[col] / ret_df[col].cummax() - 1).min()
                max_gain = (ret_df[col] / ret_df[col].cummax() - 1).max()
                var_95 = ret_df[col].quantile(0.05)
                risk_rows.append({
                    "Symbol": col,
                    "Annual Volatility": f"{vol*100:.2f}%",
                    "Annual Return": f"{mean_ret*100:.2f}%",
                    "Sharpe Ratio": f"{sharpe:.2f}",
                    "Max Drawdown": f"{max_dd*100:.2f}%",
                    "Max Gain": f"{max_gain*100:.2f}%",
                    "VaR (95%)": f"{var_95*100:.2f}%",
                })
            st.dataframe(pd.DataFrame(risk_rows), use_container_width=True, hide_index=True)

            st.markdown("**Correlation Matrix**")
            corr = ret_df.corr()
            fig_corr = go.Figure(data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.index,
                colorscale="RdBu",
                zmin=-1,
                zmax=1,
            ))
            fig_corr.update_layout(height=400, title="Return Correlation Matrix")
            st.plotly_chart(fig_corr, use_container_width=True)

            st.markdown("**Portfolio Diversification**")
            weights = np.ones(len(ret_df.columns)) / len(ret_df.columns)
            variance = float(weights @ ret_df.values.T @ ret_df.values @ weights)
            portfolio_vol = float(np.sqrt(variance) * np.sqrt(252))
            avg_vol = float(ret_df.std().mean() * np.sqrt(252))
            diversification_ratio = avg_vol / portfolio_vol if portfolio_vol != 0 else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("Portfolio Volatility (EqWt)", f"{portfolio_vol*100:.2f}%")
            c2.metric("Avg Individual Volatility", f"{avg_vol*100:.2f}%")
            c3.metric("Diversification Ratio", f"{diversification_ratio:.2f}x")

            if diversification_ratio > 1.0:
                st.success("Portfolio benefits from diversification — combined volatility is lower than the average individual volatility.")
            else:
                st.warning("Portfolio positions are highly correlated — limited diversification benefit.")
        else:
            st.info("Insufficient return data for risk computation.")
    else:
        st.info("No return data available for risk computation.")

    st.divider()

    st.subheader("Portfolio Beta")
    try:
        bench_df = fetch_prices("^CRSLDX", period="1y")
        if not bench_df.empty and len(bench_df) > 1:
            bench_ret = bench_df.set_index("Date")["Close"].pct_change().dropna()
            bench_ret = bench_ret.sort_index()

            # Align dates
            common_idx = ret_df.index.intersection(bench_ret.index)
            if len(common_idx) > 10:
                aligned_returns = ret_df.loc[common_idx]
                aligned_bench = bench_ret.loc[common_idx]

                # Calculate beta for each position
                beta_data = []
                for col in aligned_returns.columns:
                    if aligned_returns[col].std() > 0 and aligned_bench.std() > 0:
                        cov = np.cov(aligned_returns[col], aligned_bench)[0, 1]
                        bench_var = aligned_bench.var()
                        beta = cov / bench_var if bench_var != 0 else 0
                        beta_data.append({"Symbol": col, "Beta": f"{beta:.2f}"})

                if beta_data:
                    beta_df = pd.DataFrame(beta_data)
                    st.dataframe(beta_df, use_container_width=True, hide_index=True)

                    avg_beta = np.mean([float(b["Beta"]) for b in beta_data])
                    st.metric("Portfolio Beta (Equal Weight)", f"{avg_beta:.2f}")
                else:
                    st.caption("Unable to compute beta — insufficient data.")
            else:
                st.caption("Insufficient overlapping data for beta computation.")
        else:
            st.caption("Benchmark data not available.")
    except Exception:
        st.caption("Unable to compute portfolio beta.")

    st.divider()

    st.subheader("Technical Signal Summary")
    sig_rows = []
    for _, row in port_df.iterrows():
        sig_rows.append({
            "Symbol": row["symbol"],
            "Company": row["company"],
            "Technical Score": f"{row['technical_score']:.0f}%",
            "Signal": row["technical_signal"],
            "ROE": f"{row['roe']*100:.2f}%" if pd.notna(row.get("roe")) else "N/A",
            "ROCE": f"{row['roce']*100:.2f}%" if pd.notna(row.get("roce")) else "N/A",
            "Debt/Equity": f"{row['debt_equity']:.2f}" if pd.notna(row.get("debt_equity")) else "N/A",
            "Sector": row["sector"],
            "Industry": row["industry"],
        })
    st.dataframe(pd.DataFrame(sig_rows), use_container_width=True, hide_index=True)


main()
