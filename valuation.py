"""Deterministic scenario math with explicit units; assumptions remain unverified."""
import math


def number(data, key, minimum=None, strict_positive=False):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{key} must be a finite number')
    if (minimum is not None and value < minimum) or (strict_positive and value <= 0):
        raise ValueError(f'{key} is outside its valid range')
    return float(value)


def calculate_valuation(data):
    if set(data) - {'method', 'currency', 'current_price', 'years', 'scenarios'}:
        raise ValueError('Unknown valuation fields')
    method = data.get('method')
    if method not in ('equity_per_share', 'enterprise_multiple'):
        raise ValueError('Use equity_per_share or enterprise_multiple')
    currency = data.get('currency')
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError('currency must be a three-letter currency code')
    price = number(data, 'current_price', strict_positive=True)
    years = number(data, 'years', minimum=1)
    if years > 10:
        raise ValueError('Use a 1–10 year horizon')
    scenarios = data.get('scenarios')
    if not isinstance(scenarios, list) or len(scenarios) != 3 or {s.get('name') for s in scenarios if isinstance(s, dict)} != {'bear', 'base', 'bull'}:
        raise ValueError('Exactly one bear, base and bull scenario is required')
    rows = []
    for scenario in scenarios:
        if set(scenario) - {'name', 'terminal_metric', 'exit_multiple', 'terminal_net_debt', 'terminal_shares', 'cumulative_dividends_per_share'}:
            raise ValueError('Unknown scenario fields')
        metric = number(scenario, 'terminal_metric', minimum=0)
        multiple = number(scenario, 'exit_multiple', minimum=0)
        if method == 'enterprise_multiple':
            debt = number(scenario, 'terminal_net_debt')
            shares = number(scenario, 'terminal_shares', strict_positive=True)
            value = max(0.0, metric * multiple - debt) / shares
        else:
            value = metric * multiple
        dividends = number(scenario, 'cumulative_dividends_per_share', minimum=0)
        gross = (value + dividends) / price
        result = {'name': scenario['name'], 'target_price': value,
                  'price_return_pct': (value / price - 1) * 100,
                  'annualized_price_return_pct': ((value / price) ** (1 / years) - 1) * 100,
                  'terminal_wealth_return_pct': (gross - 1) * 100,
                  'annualized_terminal_wealth_return_pct': (gross ** (1 / years) - 1) * 100}
        if not all(math.isfinite(v) for k, v in result.items() if k != 'name'):
            raise ValueError('Scenario overflow; check units')
        rows.append(result)
    by_name = {row['name']: row for row in rows}
    if not by_name['bear']['target_price'] <= by_name['base']['target_price'] <= by_name['bull']['target_price']:
        raise ValueError('Bear/base/bull targets must be ordered')
    return {'method': method, 'currency': currency.upper(), 'years': years, 'current_price': price,
            'assumptions': data, 'results': rows,
            'limitations': 'Future scenario targets, not present fair value. Inputs are analyst assumptions, not verified forecasts. '
                            'Enterprise metric, debt and shares must use matching units and currency; equity metric is per share. '
                            'Dividends accumulated at horizon without reinvestment; no taxes or transaction costs. No probabilities assumed.'}
