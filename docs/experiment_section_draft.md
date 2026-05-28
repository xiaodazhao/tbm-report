# 论文实验部分草稿

## 4. Experimental Design and Results

### 4.1 Experimental Goal

The experiments aim to verify whether the proposed Construction State Twin (CST) provides an effective intermediate representation for automated TBM construction reporting. Rather than directly feeding raw engineering summaries into a large language model, the proposed method first organizes multi-source construction evidence into a structured CST and then performs report generation under state-aware prompting and evidence constraints.

The experiments focus on the following questions:

1. Whether CST-LLM outperforms a template baseline and a direct LLM baseline in report completeness.
2. Whether CST-LLM improves factual consistency and evidence traceability.
3. Whether spatial alignment, geological evidence, and prompt constraints contribute to the final report quality.

### 4.2 Experimental Cases

The current round of experiments uses six day-level cases extracted from real TBM construction data. These cases cover different reporting scenarios, including gas attention, geological attention, coupled geological-response attention, and response anomaly. The six cases are:

- `C01` (2023-09-24): gas attention case
- `C02` (2023-10-21): geological attention case
- `C03` (2023-10-24): geological attention case
- `C04` (2023-10-26): high-intensity geological attention case
- `C05` (2023-11-01): coupled attention case
- `C06` (2023-11-18): response anomaly case

For each case, a CST snapshot is exported through the experiment pipeline. Each CST instance contains temporal state, spatial state, operation state, geological state, response state, attention state, and provenance state.

### 4.3 Compared Methods

Three methods are compared in the main experiment.

#### 4.3.1 Template

This baseline uses fixed reporting templates with structured fields directly filled into predefined report text. It represents the most conservative and traditional automated reporting strategy.

#### 4.3.2 Direct-LLM

This baseline feeds operational summaries, geological summaries, gas summaries, and forward-attention summaries directly into the large language model. It does not explicitly use CST as the intermediate state representation.

#### 4.3.3 CST-LLM

This is the proposed method. It first constructs a Construction State Twin from multi-source TBM data and then builds a state-aware prompt for the large language model. The prompt enforces:

- date and scope consistency
- separation of current face observations and forward predictions
- cautious risk wording
- evidence-bounded claims

### 4.4 Evaluation Metrics

The current experiments use five evaluation metrics.

#### 4.4.1 Information Coverage Score (ICS)

ICS measures whether a report adequately covers the key reporting dimensions:

- operation and working condition
- geological situation
- gas monitoring
- forward attention

Each dimension is scored using a 0-1-2 scale:

- `0`: not covered
- `1`: partially covered
- `2`: fully covered

The final ICS is normalized to `[0,1]`.

#### 4.4.2 Factual Consistency Score (FCS)

FCS evaluates whether the generated report is consistent with the structured state and derived statistics. It is computed as:

`FCS = 1 - factual_errors_count / key_facts_count`

#### 4.4.3 Traceability Score (TS)

TS evaluates whether key report claims can be linked back to CST evidence or structured analysis outputs. It is computed as:

`TS = 1 - unsupported_claims_count / key_claims_count`

#### 4.4.4 Risk Description Reliability (RDR)

RDR evaluates whether risk-related wording is cautious and evidence-grounded. It focuses on whether the report:

- overstates attention as an already occurred hazard
- mixes current face observations with forward predictions
- states unsupported severe conclusions

RDR uses a 1-5 rating scale:

- `1`: poor
- `3`: acceptable
- `5`: highly reliable

#### 4.4.5 Expert Overall Rating (EOR)

EOR evaluates the overall engineering usefulness of the generated report, considering:

- readability
- engineering style
- completeness
- practical usability

EOR also uses a 1-5 rating scale.

### 4.5 Main Comparison Results

The main experiment compares Template, Direct-LLM, and CST-LLM on all six cases. The current aggregated results are shown below.

| Method | ICS | FCS | TS | RDR | EOR |
|---|---:|---:|---:|---:|---:|
| Template | 0.25 | 1.0000 | 1.0000 | 4.0000 | 2.0000 |
| Direct-LLM | 1.00 | 0.9167 | 0.8000 | 2.6667 | 3.5000 |
| CST-LLM | 1.00 | 1.0000 | 1.0000 | 4.8333 | 4.6667 |

The results indicate the following.

First, the Template baseline remains highly conservative, and therefore its factual consistency and traceability are strong. However, its information coverage is significantly limited.

Second, Direct-LLM substantially improves information coverage, but it suffers from weaker traceability and lower reliability in risk-related wording. This suggests that summary-to-LLM generation without an explicit state layer is more likely to produce unsupported or loosely grounded claims.

Third, CST-LLM maintains full information coverage while also preserving perfect factual consistency and traceability in the current evaluation. In addition, it achieves the highest RDR and EOR scores, indicating that CST helps the model produce more cautious, engineering-oriented, and evidence-grounded reports.

### 4.6 Traceability Analysis

Beyond the aggregate TS metric, a traceability table was constructed for all six cases. For each method, key claims were manually reviewed and linked to:

- operation state evidence
- geological evidence
- forward-attention evidence
- gas monitoring evidence
- high-attention segment summaries

The current traceability summary shows:

- Template: all reviewed claims are supported
- Direct-LLM: unsupported claims appear in `C05` and `C06`
- CST-LLM: all reviewed claims are currently supported

This confirms that CST-LLM not only improves report quality at the text level, but also strengthens the evidence linkage between report statements and structured state representations.

### 4.7 Ablation Study

To verify that the gains do not come solely from the language model itself, an ablation study was conducted on the three representative cases `C01`, `C05`, and `C06`.

The ablated variants are:

- `Full`
- `w/o Geo`
- `w/o Alignment`
- `w/o Constraints`

The current aggregated results are:

| Variant | ICS | FCS | TS | RDR | EOR |
|---|---:|---:|---:|---:|---:|
| Full | 1.00 | 1.0000 | 1.0000 | 5.0000 | 5.0000 |
| w/o Geo | 0.50 | 1.0000 | 0.8000 | 4.0000 | 3.0000 |
| w/o Alignment | 1.00 | 1.0000 | 0.8000 | 4.0000 | 4.0000 |
| w/o Constraints | 1.00 | 1.0000 | 0.8000 | 3.0000 | 4.0000 |

The ablation results show that:

- removing geological information significantly reduces information coverage and overall quality
- removing spatial alignment mainly harms traceability
- removing prompt constraints mainly harms risk wording reliability and traceability

These observations support the claim that the effectiveness of CST-LLM comes from the joint contribution of structured state organization, spatial alignment, and controlled prompting.

### 4.8 Multi-Source Contribution Study

To further evaluate the role of multi-source information, three variants were compared on `C01`, `C05`, and `C06`:

- `PLC only`
- `PLC + Geo`
- `Full`

The current results are:

| Variant | ICS | FCS | TS | RDR | EOR |
|---|---:|---:|---:|---:|---:|
| PLC only | 0.50 | 1.0000 | 0.8000 | 3.0000 | 3.0000 |
| PLC + Geo | 0.75 | 1.0000 | 1.0000 | 4.0000 | 4.0000 |
| Full | 1.00 | 1.0000 | 1.0000 | 5.0000 | 5.0000 |

This result suggests that:

- PLC-only information is insufficient for complete and cautious engineering reporting
- adding geological evidence improves claim grounding and geological description quality
- adding the full state, including gas and forward-attention information, yields the most complete and reliable report

### 4.9 State Continuity Case Analysis

The current implementation does not yet fully realize a recursive CST update in the form of `CST_t = U(CST_{t-1}, ...)`. However, a lightweight state continuity analysis has been conducted to examine whether adjacent cases exhibit interpretable changes in CST indicators.

The current continuity outputs include:

- changes in `GRS`, `RAI`, and `GRCI`
- dominant operation state transitions
- forward attention level shifts
- shared hazard labels between neighboring cases

This part is currently positioned as a case-oriented continuity analysis rather than a full quantitative dynamic-update experiment.

### 4.10 Current Limitations

The current experimental stage still has several limitations.

1. The number of cases is still small.
2. A high-quality normal case has not yet been added.
3. The current traceability analysis is complete enough for first-round validation, but still remains partly manual.
4. The recursive CST update has not yet been fully implemented and quantitatively validated.

Despite these limitations, the current results already support the main claim of the study: a construction-state-based intermediate representation is beneficial for automated TBM construction reporting with large language models.
