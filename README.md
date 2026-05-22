# 🏥 Triage-as-a-Service (TaaS) Platform

> **Real-time Telemetry Processing + AI-assisted Clinical Triage (In Progress)**

A serverless, event-driven platform designed to ingest hospital telemetry data in real time, detect anomalies, and provide AI-assisted triage recommendations using agentic LLM workflows and Hybrid RAG.

---

## 🚀 Overview

TaaS is a **B2B SaaS platform** aimed at improving clinical decision-making by combining:

* ⚡ Real-time event streaming
* 🧠 AI-powered reasoning (LLMs + Agents)
* 📊 Context-aware retrieval (Hybrid RAG)
* ☁️ Serverless, scalable architecture

The system is currently in **active development**, focusing on building a **lightweight, scalable, and cost-efficient architecture** that works within constrained environments.

---

## 🧩 Architecture

![TaaS Architecture](./architecture.png)

### 🔹 High-Level Flow

1. **Data Sources** → Patient monitors, IoT devices, hospital systems
2. **Streaming Layer** → Event ingestion via Kafka-compatible system
3. **Processing Layer** → Real-time anomaly detection
4. **AI Layer** → Agentic reasoning using LLM workflows
5. **Data Layer** → Hybrid retrieval (vector + relational)
6. **Application Layer** → APIs + dashboard

---

## ⚙️ Tech Stack

### 🔸 Streaming & Processing

* Redpanda (Kafka-compatible streaming)
* Quix Streams (Python-based stream processing / CEP)

### 🔸 AI & GenAI

* LangGraph (stateful agent workflows)
* LLM (Gemini / equivalent)
* Hybrid RAG (Vector + Relational retrieval)

### 🔸 Backend & APIs

* FastAPI (async backend services)
* REST APIs + event-driven processing

### 🔸 Data Layer

* PostgreSQL (Neon) — structured data
* Pinecone — vector embeddings

### 🔸 Frontend

* Next.js — real-time dashboard

### 🔸 Orchestration

* Upstash Workflows — async job orchestration

### 🔸 Cloud & Deployment (Planned)

* Serverless-first approach (GCP / AWS)
* Docker (for local dev + portability)

---

## 🧠 Key Features (In Progress)

* ✅ Real-time telemetry ingestion pipeline
* ✅ Event-driven architecture design
* 🔄 Anomaly detection using streaming pipelines
* 🔄 Agentic LLM workflows for triage reasoning
* 🔄 Hybrid RAG for contextual insights
* 🔄 Async backend APIs
* 🔄 Dashboard for monitoring & alerts

---

## 🏗️ System Design Highlights

* **Event-Driven Architecture**
  Enables scalable and loosely coupled services.

* **Kafka without JVM (Redpanda)**
  Chosen for lightweight deployment and lower memory footprint.

* **Agentic Workflows (LangGraph)**
  Supports multi-step reasoning instead of simple prompt-response.

* **Hybrid RAG Approach**
  Combines:

  * Vector DB → semantic understanding
  * Relational DB → structured clinical data

* **Serverless-first Thinking**
  Focus on minimizing infrastructure overhead and cost.

---

## ⚠️ Current Status

> 🚧 This project is under active development.

Current focus areas:

* Building stable streaming pipelines
* Integrating LLM workflows
* Designing robust data retrieval layers
* Improving system observability

---

## 📌 Future Enhancements

* 🔜 Advanced anomaly detection models
* 🔜 Real-time alerting system
* 🔜 Role-based dashboards (Doctors/Admins)
* 🔜 Billing & usage metering
* 🔜 Deployment on cloud serverless infrastructure

---

## 🛠️ Getting Started (Planned)

```bash
# Clone the repo
git clone https://github.com/your-username/taas-platform.git

cd taas-platform

# Start backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Start frontend
cd frontend
npm install
npm run dev
```

---

## 📚 Learning Goals

This project is being built to deepen understanding of:

* Real-time data streaming systems
* Distributed architectures
* Production-grade backend design
* Generative AI (RAG + Agents)
* Serverless system design

---

## 🤝 Contributions

This is currently a personal learning + portfolio project.
Contributions, ideas, and discussions are welcome!

---

## 📬 Contact

**Dinesh Murali Nandyala**

* LinkedIn: https://linkedin.com/in/dinesh-murali-nandyala
* Portfolio: https://dineshmurali.vercel.app
* GitHub: https://github.com/DineshMuraliNandyala

---

## ⭐ If you find this interesting

Give it a ⭐ and follow the progress!
