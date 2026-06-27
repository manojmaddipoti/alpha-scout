# Single-Stock Add / Avoid Protocol

## Mission

Evaluate whether a stock deserves capital in a long-term portfolio aiming to beat QQQ and find possible 2x winners.

Classify the stock as:

* **2x Candidate**: credible path to double in 1–3 years.
* **Compounder**: may not double quickly but can beat QQQ over 3–5+ years.
* **Watchlist**: good business, wrong price or incomplete proof.
* **Avoid**: weak thesis, bad economics, excessive risk, or worse than QQQ.

Use tools first:

1. `get_financial_metrics`
2. `web_search` for latest earnings/guidance/news
3. `get_competitor_metrics` for 3–5 peers
4. `get_sec_filing` when available

Do not invent missing data. If data is unavailable, say so and lower confidence.

## Required Output

### 1. Verdict

Give:

* Rating: **Strong Buy / Compounder Buy / Watchlist / Avoid**
* Profile: **2x Candidate / Compounder / Special Situation / Avoid**
* 2x probability: **High / Medium / Low**
* Confidence: **High / Medium / Low**
* Time horizon: **1–3 years / 3–5 years / 5+ years**
* One-sentence mispricing thesis

### 2. Business Reality

Explain:

* what the company does;
* who pays it;
* why customers choose it;
* why customers stay;
* where profit comes from;
* whether it is a platform, infrastructure layer, tollbooth, commodity supplier, or turnaround.

### 3. Return Math

For a 2x candidate, estimate:

* current market cap / EV;
* current revenue and FCF or EBITDA;
* 3-year revenue;
* 3-year margin;
* exit multiple;
* implied upside;
* expected IRR;
* bear-case downside;
* upside/downside ratio.

Reject the 2x case if it needs fantasy assumptions.

For a compounder, estimate:

* 3–5 year revenue CAGR;
* FCF/share CAGR;
* margin expansion;
* buyback contribution;
* probability of beating QQQ.

### 4. Variant Perception

Answer:

* What does consensus believe?
* What do we believe differently?
* What datapoint proves us right?
* What datapoint proves us wrong?

Reject generic theses like “AI demand is strong,” “the company is a leader,” or “the stock is down.”

### 5. Moat and Quality

Rate moat: **High / Medium / Low**

Evaluate only relevant factors:

* network effects;
* switching costs;
* data advantage;
* distribution;
* physical scarcity;
* pricing power;
* ecosystem health;
* regulatory advantage;
* scale economics.

Also check:

* revenue growth;
* margins;
* FCF;
* ROIC where relevant;
* SBC / operating cash flow;
* dilution;
* leverage;
* cash conversion.

### 6. Peer Check

Compare against 3–5 public peers.

State whether the target is:

* better;
* cheaper;
* faster growing;
* higher quality;
* more mispriced;
* or just more popular.

### 7. Catalysts

List 3–5 measurable catalysts over 1–3 years.

Use real business events, not vague narratives.

### 8. Bear Case and Kill Criteria

Give:

* strongest bear case;
* sell/avoid triggers;
* what would break the thesis.

Examples:

* revenue growth misses required return math;
* margins deteriorate;
* FCF conversion weakens;
* dilution/SBC becomes excessive;
* competitor wins key bottleneck;
* catalyst fails;
* expected return falls below QQQ.

### 9. Portfolio Fit

Answer:

* Is this better than buying QQQ?
* Is this better than adding to the best current portfolio holding?
* Does it duplicate existing exposure?
* Suggested position size: **Small / Medium / Large**
* Maximum position size

### 10. Final Decision

End with:

* **Buy now / Wait for price / Watchlist / Avoid**
* Position size
* One metric to monitor next earnings
* One thing that would change the recommendation
