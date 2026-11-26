# Search Queries for Job Scraper

<!-- SETUP: Customize these queries based on your skills, target roles, and location -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. Shipped country-agnostic CLIs include `linkedin-search` and `freehire-search`; Danish demos and any skill you add with `/add-portal` are included the same way. You do **not** need a matching `site:` line below for those CLIs to run.

The `site:` query templates in this file are the **WebSearch fallback** — for portals without a CLI, company career pages, or when a CLI fails.

**Language scope:** write every query category in every language listed in your CLAUDE.md Languages table (typically 1-2, sometimes more). A posting requiring a language you have *not* declared, as a job condition, is excluded before scoring; a posting requiring a *higher level* than you declared in a language you *do* work in is flagged for your own judgment, not excluded — see `04-job-evaluation.md`'s Language Gate, the single source of truth for this rule. Translate each category's keywords rather than machine-translating word-for-word (e.g. "Frontend Developer" -> "Desarrollador Frontend", not a literal word-for-word translation) if you work in more than one language.

## Search Sites

Primary:
- **linkedin.com/jobs** - LinkedIn job listings (filter: India / Remote / International); also covered by `linkedin-search` CLI
- **wellfound.com** - startup/AI company roles globally (strong for AI infrastructure and platform roles)

Secondary (company career pages via Google):
- Direct Google searches with `site:` filters for known target companies (see Target Company List below)

## Query Categories

### Priority 1: Cloud-Native Platform Engineering

The core function — building and owning production cloud infrastructure, often called DevOps Engineer, Platform Engineer, or SRE depending on the company.

```
site:linkedin.com/jobs "DevOps Engineer" Kubernetes India
site:linkedin.com/jobs "Platform Engineer" AWS India
site:linkedin.com/jobs "Site Reliability Engineer" Kubernetes India
site:linkedin.com/jobs "DevOps Engineer" AWS EKS India
site:wellfound.com "DevOps Engineer" OR "Platform Engineer" Kubernetes remote
```

### Priority 2: AI/LLM Infrastructure

Roles specifically building AI platform tooling, LLM gateways, MLOps pipelines — the most differentiated part of the profile.

```
site:linkedin.com/jobs "AI Infrastructure Engineer" OR "ML Platform Engineer" India
site:linkedin.com/jobs "MLOps Engineer" AWS Bedrock India
site:linkedin.com/jobs "LLM" OR "GenAI" Platform Engineer India
site:wellfound.com "AI infrastructure" OR "LLM platform" engineer
site:wellfound.com "MLOps" OR "AI platform" DevOps remote
```

### Priority 3: AIOps / Observability Engineering

Adjacent roles leveraging the observability + self-healing work — strong fit given Prometheus/Grafana/Dynatrace background.

```
site:linkedin.com/jobs "AIOps" OR "Observability Engineer" Kubernetes India
site:linkedin.com/jobs "Reliability Engineering" Prometheus Grafana India
site:wellfound.com "AIOps" OR "Observability" Engineer remote
```

### Priority 4: Broader Cloud / Backend Engineering

Wider net — senior engineer roles at target companies where platform skills transfer.

```
site:linkedin.com/jobs "Cloud Engineer" AWS Terraform India
site:linkedin.com/jobs "Backend Engineer" Kubernetes Python India
site:linkedin.com/jobs "Cloud Native" Engineer AWS India
site:linkedin.com/jobs "DevSecOps" Engineer India
site:wellfound.com "infrastructure engineer" OR "cloud engineer" remote
```

## Location Filter

When evaluating results, verify the job location matches preference:
- **Ideal:** Gurugram and central Delhi NCR (no relocation needed)
- **Acceptable:** Any city in India (Bengaluru, Mumbai, Hyderabad, Pune, Chennai, etc.) — open to relocation within India
- **Remote:** Fully remote roles anywhere are acceptable
- **International:** Open to relocation internationally with visa sponsorship; flag these for separate review

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Target Company List

Direct career page monitoring. For each company, search their careers site for DevOps / Platform / AI Infrastructure roles. Run these alongside the LinkedIn/Wellfound queries.

### Tier 1 — Dream roles (highest fit + excitement)

| Company | Why | Careers URL | Search query |
|---------|-----|-------------|--------------|
| **Zerodha** | India's largest broker; lean high-bar team; Kubernetes/Go; Bengaluru | careers.zerodha.com | `site:careers.zerodha.com DevOps OR Platform OR Infrastructure` |
| **Harness** | CI/CD DevOps platform company; Bengaluru eng hub; builds what you use daily | harness.io/company/careers | `site:harness.io/company/careers DevOps OR Platform OR SRE` |
| **Devtron** | Kubernetes DevOps platform; India-founded (Delhi NCR); building exactly what you've built | devtron.ai/careers | `site:devtron.ai/careers DevOps OR Platform OR Kubernetes` |
| **Sarvam AI** | India's leading LLM startup; Indian-language AI infra; Bengaluru | sarvam.ai/careers | `site:sarvam.ai/careers DevOps OR MLOps OR AI Infrastructure` |
| **Krutrim (by Ola)** | India's first AI unicorn; building LLM infra at scale; Delhi/Bengaluru | krutrim.com/careers | `site:krutrim.com/careers DevOps OR Platform OR AI Infrastructure` |
| **Razorpay** | Fintech India HQ; payments at scale; direct domain overlap | razorpay.com/jobs | `site:razorpay.com/jobs DevOps OR Platform OR SRE` |
| **Datadog** | Observability platform; deep Prometheus/Grafana overlap; Hyderabad office | careers.datadoghq.com | `site:careers.datadoghq.com DevOps OR SRE OR Platform Engineer India` |
| **Grafana Labs** | Core observability stack — you've shipped with their tools; fully remote-first | grafana.com/about/careers | `site:grafana.com/about/careers Platform OR DevOps OR Infrastructure` |
| **Anthropic** | AI safety + infra at the frontier; remote-ok globally | anthropic.com/careers | `site:anthropic.com/careers DevOps OR Platform OR Infrastructure` |

### Tier 2 — Strong fit (good match, high growth)

| Company | Why | Careers URL | Search query |
|---------|-----|-------------|--------------|
| **CRED** | Fintech India; highest engineering bar in India consumer tech | cred.club/careers | `site:cred.club/careers DevOps OR Platform OR Infrastructure` |
| **PhonePe** | Fintech payments; massive India scale; Kubernetes-heavy; Bengaluru | phonepe.com/en-in/careers | `site:phonepe.com/en-in/careers DevOps OR SRE OR Platform` |
| **Wise** | Global fintech payments; Bengaluru engineering hub; strong SRE/platform team | wise.jobs | `site:wise.jobs DevOps OR Platform OR SRE OR Infrastructure` |
| **Groww** | India's largest investment platform; millions of orders/day; AWS/EKS-heavy | boards.greenhouse.io/groww | `site:boards.greenhouse.io/groww DevOps OR Platform OR SRE` |
| **Paytm** | Large fintech; Noida/NCR (ideal location for you); Kubernetes/AWS | careers.paytm.com | `site:careers.paytm.com DevOps OR Platform OR Infrastructure` |
| **Setu (Pine Labs)** | Fintech API infra company; banking APIs; very engineering-focused; Bengaluru | setu.co/careers | `site:setu.co/careers DevOps OR Platform OR Infrastructure` |
| **M2P Fintech** | Fintech API/BaaS platform; millions of transactions; Chennai/Bengaluru | m2pfintech.com/careers | `site:m2pfintech.com/careers DevOps OR Platform OR Infrastructure` |
| **InfraCloud** | Kubernetes/cloud-native products + consulting; CNCF member; Pune | infracloud.io/careers | `site:infracloud.io/careers Kubernetes OR DevOps OR Platform` |
| **Acceldata** | Data observability platform; ML-infra observability; Bengaluru + US | acceldata.io/careers | `site:acceldata.io/careers DevOps OR Platform OR Infrastructure` |
| **Delhivery** | Logistics unicorn; Gurugram (ideal location); large platform engineering | delhivery.com/careers | `site:delhivery.com/careers DevOps OR Platform OR SRE` |
| **Postman** | API platform; Bengaluru HQ; large infra team; engineering-first culture | postman.com/company/careers | `site:postman.com/company/careers DevOps OR Platform OR Infrastructure` |
| **Meesho** | High-scale e-commerce; EKS/AWS-heavy; Bengaluru | meesho.io/careers | `site:meesho.io/careers DevOps OR Platform OR SRE` |
| **Cashfree** | Fintech payments India; growing infra team | cashfree.com/company/careers | `site:cashfree.com/company/careers DevOps OR Platform Engineer` |
| **Observe.AI** | AI for contact centers; ML infra at scale; Bengaluru + US | observe.ai/company/careers | `site:observe.ai/company/careers DevOps OR MLOps OR Platform` |
| **Red Hat (IBM)** | Kubernetes/OpenShift engineering; Ansible home; Pune/Bengaluru | careers.redhat.com | `site:careers.redhat.com Kubernetes OR DevOps OR Platform India` |
| **Walmart Global Tech** | Bengaluru; 3000+ engineers; global e-commerce infra at scale | careers.walmart.com | `site:careers.walmart.com DevOps OR Platform OR SRE India` |
| **Hasura** | GraphQL/data infra; strong engineering culture; Bengaluru; remote-friendly | hasura.io/careers | `site:hasura.io/careers DevOps OR Platform OR Infrastructure` |
| **Cohere** | LLM/AI infra company; remote-ok globally | cohere.com/careers | `site:cohere.com/careers DevOps OR MLOps OR AI Infrastructure` |
| **Weights & Biases** | MLOps tooling; fully remote; direct LLM infra overlap | wandb.ai/company/careers | `site:wandb.ai/company/careers Platform OR MLOps OR DevOps` |
| **Nutanix** | Cloud infra company; strong platform engineering; Bengaluru | nutanix.com/careers | `site:nutanix.com/careers DevOps OR Platform OR Cloud Infrastructure` |

### Tier 3 — Worth monitoring

| Company | Why | Careers URL | Search query |
|---------|-----|-------------|--------------|
| **Swiggy** | High-scale India infra; Kubernetes-heavy; Bengaluru | careers.swiggy.com | `site:careers.swiggy.com DevOps OR Platform OR SRE` |
| **Flipkart** | India's largest e-commerce; massive EKS footprint; Bengaluru | flipkartcareers.com | `site:flipkartcareers.com DevOps OR Platform OR Infrastructure` |
| **Zepto** | High-growth quick-commerce; strong infra scaling needs | zeptonow.com/careers | `site:zeptonow.com/careers DevOps OR Platform OR Infrastructure` |
| **Juspay** | Fintech payments India; strong engineering culture | juspay.in/careers | `site:juspay.in/careers DevOps OR Platform OR Infrastructure` |
| **Fi Money (epifi)** | Neobank; engineering-first culture; Kubernetes-heavy; Bengaluru | fi.money/careers | `site:fi.money/careers DevOps OR Platform OR Infrastructure` |
| **Jupiter Money** | Neobank; AWS/Kubernetes infra; Bengaluru | jupiter.money/careers | `site:jupiter.money/careers DevOps OR Platform OR Infrastructure` |
| **Navi** | Sachin Bansal's fintech; strong engineering culture; Bengaluru | navi.com/careers | `site:navi.com/careers DevOps OR Platform OR Infrastructure` |
| **OfBusiness** | B2B commerce unicorn; Gurugram (ideal location); scaling fast | ofbusiness.in/careers | `site:ofbusiness.in/careers DevOps OR Platform OR Infrastructure` |
| **BrowserStack** | Dev tools SaaS; India HQ Mumbai; cloud infra at scale | browserstack.com/careers | `site:browserstack.com/careers DevOps OR Platform OR Infrastructure` |
| **Porter** | Logistics startup India; scaling infra fast; Bengaluru | porter.in/careers | `site:porter.in/careers DevOps OR Platform OR SRE` |
| **Sprinklr** | AI SaaS; Gurugram office (ideal location); large engineering teams | sprinklr.com/careers | `site:sprinklr.com/careers DevOps OR Platform OR Infrastructure` |
| **Cars24** | Auto-tech unicorn; Gurugram (ideal); AWS/Kubernetes scale | cars24.com/careers | `site:cars24.com/careers DevOps OR Platform OR Infrastructure` |
| **Freshworks** | SaaS; Chennai/Bengaluru; large platform team | freshworks.com/company/careers | `site:freshworks.com/company/careers DevOps OR Platform OR SRE` |
| **CleverTap** | Mobile engagement SaaS; Mumbai; large Kubernetes/AWS infra | clevertap.com/careers | `site:clevertap.com/careers DevOps OR Platform OR Infrastructure` |
| **Hugging Face** | AI/ML platform; LLM infra at scale; remote-ok | apply.workable.com/hugging-face | `site:apply.workable.com/hugging-face DevOps OR MLOps OR Platform` |
| **HashiCorp (IBM)** | Terraform, Vault — you use these daily; IBM India engineering centers | ibm.com/careers | `site:ibm.com/careers HashiCorp OR Terraform Platform Engineer India` |

### India Big Tech (high volume, good for benchmarking offers)

| Company | Careers URL | Search query |
|---------|-------------|--------------|
| **Google India** | careers.google.com | `site:careers.google.com SRE OR Platform Engineer India` |
| **Amazon / AWS India** | amazon.jobs | `site:amazon.jobs DevOps OR Platform OR SRE India` |
| **Microsoft India** | careers.microsoft.com | `site:careers.microsoft.com DevOps OR Platform OR Cloud Engineer India` |
| **Atlassian** | atlassian.com/company/careers | `site:atlassian.com/company/careers DevOps OR SRE OR Platform India` |

---

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
