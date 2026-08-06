from data.fetch_fundamentals import fetch_fundamentals


def main():
    symbol = "RELIANCE.NS"
    f = fetch_fundamentals(symbol)
    print("Symbol:", f.get("Symbol"))
    print("Company:", f.get("Company"))
    print("Fundamentals source:", f.get("fundamentals_source"))
    print("Quarterly meta:", f.get("quarterly_meta"))
    q = f.get("quarterly_financials")
    if q is None:
        print("No quarterly financials available via provider.")
        return

    # attempt to find EPS labels
    eps_label = next((l for l in ["Diluted EPS", "Basic EPS", "EPS"] if l in q.index), None)
    print("EPS label found:", eps_label)
    if eps_label:
        try:
            print(q.loc[eps_label].to_string())
        except Exception:
            print(list(q.loc[eps_label]))


if __name__ == "__main__":
    main()
