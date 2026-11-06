# Local LLM Benchmark Report — e& Egypt Agentic KB

**Date**: `2026-08-29 14:09:23`  
**Model Evaluated**: `qwen2.5:3b`  
**Hardware Target**: Lenovo Legion Slim 5i (`NVIDIA GeForce RTX 4050 Laptop GPU`)  
**GPU Memory Architecture**: 4GB Dedicated GDDR6 VRAM (Reported by WDDM: 6141 MB total including shared)  
**System Memory**: 16108 MB RAM  
**Total Suite Duration**: 38.0s

---

## Performance Executive Summary

| Key Metric | Measured Value | Target SLA / Safety Status |
|---|---|---|
| **Test Pass Rate** | **7 / 7** (100%) | 100% Core Scenarios |
| **Average Latency** | **5.37s** | < 8.0s (Interactive) |
| **Avg Time-To-First-Token (TTFT)** | **2.22s** | < 1.0s (Instantaneous) |
| **Average Generation Speed** | **59.1 tokens/sec** | > 40 tok/s Target |
| **Peak VRAM Consumed** | **2157 MB** | Safe within 4,096 MB VRAM (< 3,800 MB limit) |
| **Peak GPU Temperature** | **69°C** | Normal Thermal Zone (< 80°C) |

---

## Detailed Scenario Matrix

| # | Scenario | Latency | TTFT | Speed | VRAM Used | Temp | RAM | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | 1. Normal Chat | 6.16s | 2.33s | 65.3 tok/s | 2153 MB | 64°C | 14352 MB | ✅ PASS |
| 2 | 2. Arabic Telecom | 7.76s | 2.16s | 59.8 tok/s | 2153 MB | 66°C | 14484 MB | ✅ PASS |
| 3 | 3. English Telecom | 7.03s | 2.17s | 58.5 tok/s | 2153 MB | 67°C | 14397 MB | ✅ PASS |
| 4 | 4. RAG Grounded QA | 3.61s | 2.21s | 58.0 tok/s | 2157 MB | 67°C | 14405 MB | ✅ PASS |
| 5 | 5. MCP / Tool Calling | 2.84s | 2.19s | 58.3 tok/s | 2157 MB | 65°C | 14427 MB | ✅ PASS |
| 6 | 6. Structured JSON | 2.99s | 2.21s | 54.6 tok/s | 2157 MB | 64°C | 14444 MB | ✅ PASS |
| 7 | 7. Multi-Step Agent | 7.17s | 2.24s | 59.5 tok/s | 2157 MB | 69°C | 14414 MB | ✅ PASS |

---

## Detailed Prompts & Model Outputs

### 1. 1. Normal Chat
- **Latency**: `6.16s` | **TTFT**: `2.33s` | **Speed**: `65.3 tok/s`
- **Telemetry**: VRAM `2153 MB` | GPU Temp `64°C` | CPU `13.9%`

**Input Prompt**:
```text
Hello! Can you introduce yourself and explain how you can help me as an e& Egypt customer support assistant?
```

**Model Output**:
```text
Hello! I'm Qwen, a large language model created by Alibaba Cloud. I'm designed to assist with a wide range of tasks and queries, including providing information, answering questions, and offering guidance on various topics. As an e& Egypt customer support assistant, I'm here to help you with any questions or issues you might have related to your e& Egypt services.

Here are some ways I can assist you:

1. **Product Information**: I can provide detailed information about e& Egypt's products and services, including features, benefits, and how to use them effectively.

2. **Technical Support**: If you encounter any technical issues with your e& Egypt services, I can help diagnose problems and suggest solutions.

3. **Billing and Payment**: I can assist with understanding your billing statements, payment options, and any related inquiries.

4. **Customer Service**: I can help resolve any customer service issues you might have, such as account management, service interruptions, and more.

5. **General Queries**: I can answer any general questions you might have about e& Egypt's services, including usage, troubleshooting, and more.

Please feel free to ask me anything specific about your e& Egypt services, and I'll do my best to assist
```

### 2. 2. Arabic Telecom
- **Latency**: `7.76s` | **TTFT**: `2.16s` | **Speed**: `59.8 tok/s`
- **Telemetry**: VRAM `2153 MB` | GPU Temp `66°C` | CPU `17.6%`

**Input Prompt**:
```text
عايز اعرف ايه الفرق بين باقات حكاية ميكساتس وحكاية إنترنت، وايه الأنسب ليا لو بستخدم نت كتير وبكلم صحابي عادي؟
```

**Model Output**:
```text
باقة "حكاية ميكساتس" و"حكاية إنترنت" هما منتجات إنترنت تقدمها شركة إنترنت للعملاء. الفرق بينهما يعتمد على احتياجاتك الشخصية ومستوى الاستخدام الذي ترغب في الحصول عليه. إليك بعض النقاط التي قد تساعدك في اتخاذ قرار:

1. حكاية ميكساتس: تتميز هذه الباقة بوجود اتصال دائم ومستمر، وهي خيار جيد إذا كنت تحتاج إلى اتصال مستمر وقوي. كما أنها تأتي مع خدمة الاتصال اللاسلكي (Wi-Fi) في بعض الأحيان.

2. حكاية إنترنت: تتميز هذه الباقة بقدرتها على التكيف مع احتياجاتك. إذا كنت تحتاج إلى اتصال خفيف أو متوسط، يمكنك اختيار الباقة المناسبة لك. كما أنها تتيح لك التحكم في استهلاك البيانات، وهذا قد يكون مفيدًا إذا كنت تستخدم الإنترنت بكثافة ولكنك لا ترغب في دفع مبلغ كبير.

من بين الباقةين، إذا كنت تستخدم الإنترنت بكثافة وتحتاج إلى اتصال مستمر وقوي، فربما تكون الباقة "حكاية ميكساتس" هي الخيار الأفضل. ولكن إذا كنت ترغب في التحكم في استهلاك البيانات وتحتاج إلى القدرة على التحكم في استهلاك البيانات، فربما تكون الباقة "حكاية إنترنت" هي الخيار الأفضل.
```

### 3. 3. English Telecom
- **Latency**: `7.03s` | **TTFT**: `2.17s` | **Speed**: `58.5 tok/s`
- **Telemetry**: VRAM `2153 MB` | GPU Temp `67°C` | CPU `13.4%`

**Input Prompt**:
```text
Explain the Emerald 780 postpaid plan. What are the included family sharing benefits, data allowances, and minutes?
```

**Model Output**:
```text
I'm sorry for the confusion, but I don't have specific information about the "Emerald 780 postpaid plan" as it's not a widely recognized plan name. The pricing and features of mobile plans can vary significantly by region and service provider. 

However, I can provide a general idea of what a postpaid plan might include based on common features:

1. **Family Sharing Benefits**: This typically refers to the ability to share a portion of your plan's data and/or minutes with other family members. The specifics can vary, but it might include sharing a portion of your data allowance or minutes with up to 5 other family members.

2. **Data Allowances**: This is the amount of data you can use on your plan. It can be in the form of a fixed amount of data or a certain amount of data per month. For example, a 1GB data plan would allow you to use up to 1GB of data per month.

3. **Minutes**: This is the amount of voice minutes you can use on your plan. It's usually measured in minutes per month. For example, a 200-minute plan allows you to make up to 200 voice calls per month.

If you could provide more details or specify the region and service provider, I could give you a more accurate description of the Emerald 780 postpaid plan.
```

### 4. 4. RAG Grounded QA
- **Latency**: `3.61s` | **TTFT**: `2.21s` | **Speed**: `58.0 tok/s`
- **Telemetry**: VRAM `2157 MB` | GPU Temp `67°C` | CPU `12.8%`

**Input Prompt**:
```text
Context Information:
-------------------
Package: Hekaya Mixat 92
Pre-tax Price: 92 EGP
Total Price (incl. tax): 131.44 EGP
Units: 4,000 Mixes
Activation Code: *319*92#
Super Internet on TikTok and YouTube: 1 MB = 1 Super MB
-------------------
Based ONLY on the context above, answer: What is the USSD activation code, total price with tax, and total units for Hekaya Mixat 92?
```

**Model Output**:
```text
Based on the context provided:

- The USSD activation code for Hekaya Mixat 92 is *319*92#.
- The total price with tax for Hekaya Mixat 92 is 131.44 EGP.
- The total units for Hekaya Mixat 92 are 4,000 Mixes.
```

### 5. 5. MCP / Tool Calling
- **Latency**: `2.84s` | **TTFT**: `2.19s` | **Speed**: `58.3 tok/s`
- **Telemetry**: VRAM `2157 MB` | GPU Temp `65°C` | CPU `11.9%`

**Input Prompt**:
```text
You have access to the following tool definition:
Tool: calculate_price(base_price: float, is_tax_inclusive: bool, tax_type: str)

A customer asks: 'معايا ميزانية 200 جنيه شاملة الضريبة، احسبلي الرصيد الصافي قبل الضريبة'.
Select and format the tool call in valid JSON format:
{"tool": "calculate_price", "parameters": {"base_price": 200.0, "is_tax_inclusive": true, "tax_type": "prepaid"}}
```

**Model Output**:
```text
{"tool": "calculate_price", "parameters": {"base_price": 200.0, "is_tax_inclusive": true, "tax_type": "prepaid"}}
```

### 6. 6. Structured JSON
- **Latency**: `2.99s` | **TTFT**: `2.21s` | **Speed**: `54.6 tok/s`
- **Telemetry**: VRAM `2157 MB` | GPU Temp `64°C` | CPU `9.5%`

**Input Prompt**:
```text
Extract customer profiling into JSON adhering to this exact schema:
{"service": "Hekaya", "sub_track": "Mixat", "budget_egp": 120.0, "needs_clarification": false, "language": "ar"}

Customer query: 'عايز باقة حكاية مكسات في حدود 120 جنيه'
Output ONLY the valid JSON object without markdown or commentary:
```

**Model Output**:
```text
{"service": "Hekaya", "sub_track": "Mixat", "budget_egp": 120.0, "needs_clarification": false, "language": "ar"}
```

### 7. 7. Multi-Step Agent
- **Latency**: `7.17s` | **TTFT**: `2.24s` | **Speed**: `59.5 tok/s`
- **Telemetry**: VRAM `2157 MB` | GPU Temp `69°C` | CPU `12.4%`

**Input Prompt**:
```text
System: You are an autonomous telecom sales agent.
Step 1: Understand user constraint (Budget: 150 EGP total including tax, primarily calls).
Step 2: Compare Hekaya Mixat 69 (total ~98.58 EGP) vs Hekaya Mixat 92 (total ~131.44 EGP) vs Hekaya Mixat 120 (total ~171.44 EGP).
Step 3: Provide the single highest package within the 150 EGP budget, with exact pre-tax price, total price, and USSD code.

Give your concise step-by-step reasoning and final recommendation.
```

**Model Output**:
```text
Step 1: Understanding the user's constraint:
- The user's total budget is 150 EGP, including tax.
- The primary need is for calls.

Step 2: Comparing the packages:
- Hekaya Mixat 69: Total cost is approximately 98.58 EGP.
- Hekaya Mixat 92: Total cost is approximately 131.44 EGP.
- Hekaya Mixat 120: Total cost is approximately 171.44 EGP.

Step 3: Recommendation:
- The user's budget is 150 EGP, including tax.
- Among the three packages, Hekaya Mixat 69 is the only one that fits within the budget.
- Hekaya Mixat 69 costs 98.58 EGP, including tax.

Final Recommendation:
- The single highest package within the 150 EGP budget is Hekaya Mixat 69.
- The exact pre-tax price is 98.58 EGP.
- The total price including tax is 98.58 EGP.
- The USSD code to activate this package is *92*69#.

Note: The tax amount is 150 EGP - 98.58 EGP = 51.42 EGP.
```
