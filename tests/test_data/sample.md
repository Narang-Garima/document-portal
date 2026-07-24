# ShopBuddy — Interview Prep Doc

## Tech Stack (from your project card)
LangGraph · FastAPI · AWS EKS · Groq · RAGAS · Kubernetes · MCP

## Metrics to be ready to explain
- 0.85 Context Precision (RAGAS evaluation)
- 40% faster response times through optimization
- 99% uptime with zero-downtime deployments
- 10× cost reduction using Groq vs GPT-4

---

## 1. The 30-Second Pitch
*(Use for: recruiter screens, "walk me through your resume")*

"ShopBuddy is an agentic RAG assistant for e-commerce — it handles product recommendations and contextual search using LangGraph for orchestration. I focused heavily on production concerns: I evaluated retrieval quality with RAGAS to hit 0.85 context precision, cut inference cost 10x by switching from GPT-4 to Groq, and deployed it on Kubernetes/EKS with zero-downtime rollouts."

**Fill in your own number/story here**: which single result are you proudest of, and why? That should be your closing line.

---

## 2. The 1-Minute Pitch
*(Use for: "tell me about a project," hiring manager rounds)*

Structure: Problem → Architecture → Key decision → Result

- **Problem**: E-commerce search/recommendations often fail on ambiguous or conversational queries that simple keyword/embedding search can't handle well — need an agent that can reason about intent, not just retrieve.
- **Architecture**: LangGraph orchestrates the agent loop — retrieval, reasoning, and response generation as explicit graph nodes rather than a single prompt. FastAPI serves it, deployed on Kubernetes (EKS) for scalability.
- **Key decision**: Chose Groq over GPT-4 for inference — [YOU FILL IN: was it latency, cost, or both that drove this? Groq's known for very fast token generation, which matters for a conversational shopping assistant where response speed affects UX]
- **Result**: 0.85 context precision on RAGAS, 40% latency improvement, 99% uptime, 10x cheaper inference.

**Action item**: rehearse this out loud until it's under 60 seconds without rushing.

---

## 3. The 10-Minute Deep Dive
*(Use for: technical rounds, "walk me through the code")*

Cover these in order, and for each, have a **one-sentence "why"** ready:

1. **Why LangGraph and not plain LangChain/CrewAI?**
   Fill in: did you need explicit state control, conditional routing between retrieval/reasoning steps, or cycles (e.g., re-retrieve if confidence is low)? This is *the* most common framework-choice question.

2. **Retrieval design**
   What's in your vector store, how is it chunked, what embedding model, and — critically — what made retrieval good enough to hit 0.85 precision? Did you tune chunk size, add reranking, or filter by metadata?

3. **RAGAS evaluation**
   Which RAGAS metrics did you track (context precision, faithfulness, answer relevancy)? How did you build your eval set — real queries, synthetic, or both? What was the score *before* your optimizations, so you can show the delta?

4. **Groq vs GPT-4 tradeoff**
   Be ready for: "What did you give up by switching?" (e.g., Groq-hosted open models may have different reasoning quality than GPT-4 for complex multi-step queries). A good answer names the tradeoff honestly, not just the win.

5. **Kubernetes/EKS deployment**
   What does "zero-downtime deployment" actually mean in your setup — rolling updates? readiness probes? How is the app scaled (HPA on CPU/latency)? If you didn't configure autoscaling yourself, be honest about what you set up vs what's default.

6. **MCP usage**
   What did you use Model Context Protocol for specifically — connecting a tool/data source to the agent? This is a newer, high-signal keyword; be ready to explain in plain terms what problem MCP solved for you versus just calling a function directly.

7. **A bug you hit**
   Pick one real failure (rate limiting, retrieval returning irrelevant chunks, agent looping) and narrate: what broke, how you diagnosed it, what you changed. This is often the most convincing 2 minutes of a technical interview.

---

## 4. "Why X over Y" — Answers to Draft Yourself

Fill these in with your actual reasoning (I can help polish once you draft):

| Question | Your answer |
|---|---|
| Why LangGraph over CrewAI or AutoGen? | |
| Why Groq over GPT-4/Claude? | |
| Why RAGAS over building your own eval script? | |
| Why Kubernetes/EKS over a simpler host (Render/EC2)? | |
| What would you change if traffic grew 100x? | |
| How do you prevent stale/incorrect product data in retrieval? | |
| How would you add multi-turn conversation memory to this? | |

---

## 5. Likely Curveball Questions

- "Your RAGAS precision is 0.85 — what's in the other 15%? What kinds of queries still fail?"
- "How do you know the 40% speed improvement isn't just from switching to Groq — what else did you optimize?"
- "What happens if the Groq API is down — do you have a fallback model?"
- "How do you handle a user asking about a product that doesn't exist in your catalog — does the agent hallucinate or gracefully decline?"
- "Walk me through what happens end-to-end when a user types a query — every hop."

---

## Next Step
Fill in the blanks above with your real answers (especially section 4), and send them back — I'll help tighten the phrasing and flag any answer that sounds rehearsed-but-shallow versus genuinely understood.
