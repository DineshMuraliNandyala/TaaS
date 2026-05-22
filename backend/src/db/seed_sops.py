#!/usr/bin/env python3
"""
Seeds the clinical_sops table with 12 realistic clinical SOPs.
Generates embeddings via Gemini text-embedding-004 (768 dimensions).
Run once before starting the agent:
    python -m backend.src.db.seed_sops
"""
import asyncio
import sys

from google import genai
from google.genai import types
from sqlalchemy import text

sys.path.insert(0, ".")

from backend.src.config import settings
from backend.src.db.postgres import get_session
from backend.src.logger import get_logger

log = get_logger(__name__)

client = genai.Client(api_key=settings.gemini_api_key)

# ── SOP Corpus ───────────────────────────────────────────────────────────────

SOPS = [
    {
        "title": "Acute Cardiogenic Shock — Initial Management Protocol",
        "category": "Cardiac",
        "tags": ["shock", "hypotension", "tachycardia", "cardiac", "haemodynamic"],
        "content": """
        ACUTE CARDIOGENIC SHOCK — INITIAL MANAGEMENT PROTOCOL
        Definition: Cardiogenic shock is defined as sustained hypotension (SBP <90 mmHg
        for >30 minutes) due to primary cardiac dysfunction, with signs of end-organ
        hypoperfusion despite adequate intravascular volume.
        Immediate actions (0-15 minutes):
        1. Activate cardiac catheterisation lab if STEMI is suspected.
        2. Insert large-bore IV access (2x 16G minimum) and arterial line.
        3. Administer oxygen to maintain SpO2 >94%. Consider early intubation if RR >25.
        4. 12-lead ECG within 10 minutes of presentation.
        5. Bloods: FBC, U&E, LFTs, troponin, lactate, ABG, coagulation screen.
        6. Bedside echo to assess LV function, pericardial effusion, wall motion.
        Haemodynamic targets: MAP >65 mmHg, urine output >0.5 mL/kg/hr.
        Vasopressor of choice: Norepinephrine 0.1-0.3 mcg/kg/min titrated to MAP.
        Avoid fluids in pure cardiogenic shock — may worsen pulmonary oedema.
        Contraindications: Avoid beta-blockers in acute decompensation. Avoid high-dose
        diuretics without confirmed volume overload via CVP or echo.
        """,
    },
    {
        "title": "Sepsis and Septic Shock — Hour-1 Bundle",
        "category": "Infectious Disease",
        "tags": ["sepsis", "SIRS", "shock", "infection", "lactate", "antibiotics"],
        "content": """
        SEPSIS AND SEPTIC SHOCK — SURVIVING SEPSIS HOUR-1 BUNDLE
        Definition: Sepsis = life-threatening organ dysfunction caused by dysregulated
        host response to infection. SIRS criteria: 2+ of [Temp >38°C or <36°C,
        HR >90, RR >20, WBC >12K or <4K].
        Within 1 hour of recognition:
        1. Measure lactate. If lactate >2 mmol/L, treat as septic shock.
        2. Obtain blood cultures (2 sets) BEFORE starting antibiotics.
        3. Administer broad-spectrum IV antibiotics within 1 hour.
           - Community-acquired: Piperacillin-tazobactam 4.5g IV q6h
           - Hospital-acquired/ICU: Meropenem 1g IV q8h + Vancomycin
        4. Give 30 mL/kg crystalloid bolus for hypotension or lactate ≥4 mmol/L.
        5. Apply vasopressors for MAP <65 mmHg despite resuscitation.
           First line: Norepinephrine 0.1 mcg/kg/min, titrate to MAP ≥65.
        Reassess within 3 hours: repeat lactate if initial >2. Target lactate clearance >10%.
        Caution in CKD patients: reduce fluid bolus, monitor for fluid overload.
        Caution with contrast imaging if eGFR <30.
        """,
    },
    {
        "title": "Acute Respiratory Failure — Oxygen Therapy and NIV Protocol",
        "category": "Respiratory",
        "tags": ["hypoxia", "SpO2", "respiratory failure", "oxygen", "NIV", "CPAP"],
        "content": """
        ACUTE RESPIRATORY FAILURE — OXYGEN THERAPY AND NIV PROTOCOL
        Indications for urgent oxygen therapy: SpO2 <94% in adults,
        SpO2 <88% in known COPD patients (risk of hypercapnic drive suppression).
        Oxygen delivery targets:
        - Non-COPD patients: SpO2 94-98% via non-rebreather mask at 15L/min.
        - Known COPD/type 2 respiratory failure: SpO2 88-92% via Venturi mask 28%.
        Escalation to NIV (CPAP/BiPAP):
        Criteria: Persisting SpO2 <92% on 60% FiO2, RR >25, accessory muscle use.
        Initial BiPAP settings: IPAP 12-16 cmH2O, EPAP 4-6 cmH2O, FiO2 40%.
        Indications for intubation: Deteriorating GCS, exhaustion, SpO2 <88% on
        maximum NIV, haemodynamic instability.
        Monitoring: ABG at 1h and 4h post initiation of NIV.
        Caution: Avoid high-flow oxygen in COPD patients — risk of hypercapnia.
        """,
    },
    {
        "title": "Hypertensive Emergency — Rapid Assessment and Treatment Protocol",
        "category": "Cardiac",
        "tags": ["hypertension", "hypertensive crisis", "SBP", "blood pressure", "stroke"],
        "content": """
        HYPERTENSIVE EMERGENCY — RAPID ASSESSMENT AND TREATMENT PROTOCOL
        Definition: Hypertensive emergency = SBP >180 mmHg AND evidence of
        acute end-organ damage (AKI, hypertensive encephalopathy, aortic dissection,
        acute LV failure, hypertensive retinopathy grade III/IV).
        Distinguish from urgency (SBP >180 without organ damage — less acute).
        Immediate assessment:
        1. ECG, chest X-ray, urine dip for proteinuria.
        2. Bloods: U&E, creatinine, FBC, troponin, LFTs.
        3. CT head if neurological symptoms.
        4. Fundoscopy within 1 hour.
        Blood pressure targets:
        - Reduce MAP by no more than 25% in first hour (too rapid = stroke/MI risk).
        - Target SBP 150-160 mmHg at 1 hour, then 135-145 over 24h.
        Drug of choice (IV): Labetalol 20mg IV bolus, repeat q10min (max 300mg).
        Alternative: Nicardipine infusion 5-15 mg/hr IV.
        Avoid: Sublingual nifedipine (excessive rapid drop). Hydralazine (unpredictable).
        Special cases: In suspected aortic dissection, target SBP <120 mmHg within 20 min.
        """,
    },
    {
        "title": "Bradycardia — Symptomatic Assessment and Pacing Protocol",
        "category": "Cardiac",
        "tags": ["bradycardia", "heart rate", "pacing", "atropine", "syncope"],
        "content": """
        SYMPTOMATIC BRADYCARDIA — ASSESSMENT AND MANAGEMENT PROTOCOL
        Definition: Symptomatic bradycardia = HR <45 bpm with associated
        haemodynamic instability, syncope, chest pain, or altered consciousness.
        Immediate assessment:
        1. 12-lead ECG: identify rhythm (sinus bradycardia, AV block degree, junctional).
        2. Check medications: beta-blockers, calcium channel blockers, digoxin toxicity.
        3. Exclude reversible causes: hypothyroidism, hyperkalaemia, hypothermia.
        First-line treatment (haemodynamically unstable):
        - Atropine 500 mcg IV bolus, repeat every 3-5 minutes (max 3mg total).
        - If no response to atropine: transcutaneous pacing at rate 70-80 bpm.
        - Pacing current: start 40mA, increase until capture (QRS follows spike).
        Second-line (atropine-resistant): Isoprenaline 5 mcg/min IV infusion.
        Escalation: Transvenous pacing for persistent instability.
        Avoid: Atropine in 2nd degree Mobitz type II and complete heart block
        (may paradoxically worsen block).
        """,
    },
    {
        "title": "Acute Pulmonary Oedema — Emergency Management",
        "category": "Cardiac",
        "tags": ["pulmonary oedema", "heart failure", "dyspnoea", "furosemide", "CPAP"],
        "content": """
        ACUTE PULMONARY OEDEMA — EMERGENCY MANAGEMENT PROTOCOL
        Clinical presentation: Acute dyspnoea, SpO2 <94%, bilateral crackles,
        frothy sputum, hypertension or hypotension, S3 gallop.
        Immediate actions:
        1. Sit patient upright (reduces preload).
        2. High-flow oxygen via non-rebreather mask. Start CPAP early if available.
        3. IV access and monitoring (ECG, BP, SpO2 continuous).
        4. 12-lead ECG to exclude precipitating MI.
        Pharmacological management:
        - IV Furosemide 40-80mg IV stat (double usual oral dose if on chronic diuretics).
        - GTN (nitrates): 0.5-1mg sublingual, then IV infusion 2-10 mg/hr if SBP >110.
        - Opiates (Morphine 2.5-5mg IV): reduces anxiety and preload — use cautiously.
        Caution in patients already on Furosemide (PT-003, PT-005): may require
        higher doses; monitor for hypokalaemia and acute kidney injury.
        Avoid: Fluids, beta-blockers in acute decompensation.
        Target: SpO2 >95%, RR <20, HR <100, SBP 100-140 within 1 hour.
        """,
    },
    {
        "title": "Hypoglycaemia in Diabetic Inpatients — Detection and Correction",
        "category": "Endocrine",
        "tags": ["diabetes", "hypoglycaemia", "insulin", "glucose", "BM check"],
        "content": """
        HYPOGLYCAEMIA IN DIABETIC INPATIENTS — DETECTION AND CORRECTION PROTOCOL
        Definition: Blood glucose <4.0 mmol/L in a hospitalised diabetic patient.
        Severe hypoglycaemia: <2.8 mmol/L or patient unable to self-treat.
        Risk factors for severe hypoglycaemia in inpatients:
        Reduced oral intake, insulin dose not adjusted for fasting, sulphonylureas,
        renal impairment (reduced insulin clearance — highly relevant for PT-005 CKD stage 4).
        Immediate management (conscious patient):
        1. Give 150-200 mL fruit juice OR 3-4 glucose tablets.
        2. Recheck BM in 15 minutes.
        3. If corrected, give long-acting carbohydrate snack.
        Immediate management (unconscious / unable to swallow):
        1. IV 75-100 mL of 20% glucose (or 150-200 mL of 10% glucose).
        2. If no IV access: Glucagon 1mg IM.
        3. Recheck BM every 15 minutes until stable.
        Medication review: Hold insulin dose pending senior review. Review basal insulin
        if recurrent hypoglycaemia. Caution with Metformin in AKI (risk of lactic acidosis).
        """,
    },
    {
        "title": "Acute Kidney Injury — Recognition and Stage-Based Management",
        "category": "Renal",
        "tags": ["AKI", "kidney", "creatinine", "urine output", "CKD", "nephrotoxic"],
        "content": """
        ACUTE KIDNEY INJURY — RECOGNITION AND STAGE-BASED MANAGEMENT
        KDIGO Staging:
        Stage 1: Creatinine ×1.5-1.9 baseline or urine output <0.5 mL/kg/hr for 6-12h.
        Stage 2: Creatinine ×2-2.9 baseline or UO <0.5 mL/kg/hr for ≥12h.
        Stage 3: Creatinine ×3 baseline or >354 μmol/L or UO <0.3 mL/kg/hr for ≥24h.
        Immediate actions for AKI Stage 2+:
        1. Stop nephrotoxic drugs: NSAIDs, aminoglycosides, ACE inhibitors in acute setting.
        2. Hold Metformin (risk of lactic acidosis). Hold contrast imaging.
        3. Fluid challenge: 250-500 mL crystalloid over 15-30 minutes if no fluid overload.
        4. Strict input/output monitoring (urinary catheter).
        5. Check for obstructive cause: bladder scan, renal ultrasound.
        6. Bloods: daily U&E, creatinine, bicarbonate, potassium.
        High-risk patients on this ward: PT-003 (CKD Stage 3), PT-005 (CKD Stage 4).
        Medication caution: Lisinopril, Furosemide doses require daily review in AKI.
        Renal replacement therapy criteria: refractory hyperkalaemia, uraemia, fluid overload.
        """,
    },
    {
        "title": "Tachycardia — Broad and Narrow Complex Differential and Management",
        "category": "Cardiac",
        "tags": ["tachycardia", "heart rate", "SVT", "AF", "VT", "ECG"],
        "content": """
        TACHYCARDIA — DIFFERENTIAL DIAGNOSIS AND MANAGEMENT PROTOCOL
        First step: Is the patient haemodynamically stable?
        Unstable (SBP <90, altered consciousness, chest pain): immediate DC cardioversion.
        Stable: determine QRS morphology on 12-lead ECG.
        Narrow complex tachycardia (QRS <120ms):
        - Regular: likely SVT or atrial flutter. Vagal manoeuvres first.
          Adenosine 6mg rapid IV bolus, followed by 12mg if no response.
        - Irregular: likely atrial fibrillation. Rate control with beta-blocker
          (Metoprolol 5mg IV) if no HF, or digoxin if HF present.
        Broad complex tachycardia (QRS >120ms):
        - Assume VT until proven otherwise.
        - Amiodarone 300mg IV over 20-60 minutes if stable.
        - If deteriorates: immediate defibrillation 200J biphasic.
        Caution: Do NOT give Verapamil for broad complex tachycardia — risk of arrest.
        In patients with known CHF (PT-005): prefer Amiodarone over beta-blockers.
        """,
    },
    {
        "title": "Fever and Suspected Infection in ICU — Assessment and Antibiotic Stewardship",
        "category": "Infectious Disease",
        "tags": ["fever", "temperature", "infection", "antibiotics", "blood cultures", "ICU"],
        "content": """
        FEVER IN ICU — ASSESSMENT AND ANTIBIOTIC STEWARDSHIP PROTOCOL
        Definition: Temperature >38.3°C on two occasions 1h apart, or single
        temperature >38.9°C in ICU patient.
        Source identification (within 1 hour of fever spike):
        1. Blood cultures ×2 (peripheral and central if CVC in situ).
        2. Urine MC&S (catheter specimen if IDC in situ).
        3. Sputum/endotracheal aspirate culture if ventilated.
        4. Review IV line sites, wounds, and drain sites.
        5. CXR to exclude new pneumonia.
        Empirical antibiotic selection (ICU, hospital-acquired):
        - No known MRSA risk: Piperacillin-tazobactam 4.5g IV q6h.
        - MRSA risk or recent healthcare exposure: Add Vancomycin 25 mg/kg loading.
        - Immunocompromised/neutropaenic: Add antifungal cover (Fluconazole 400mg).
        Antibiotic stewardship: De-escalate within 48-72h based on culture sensitivity.
        Target CRP reduction >50% at 48h as marker of adequate source control.
        Caution with Vancomycin in patients with CKD — dose by AUC/MIC monitoring.
        """,
    },
    {
        "title": "Medication Safety — High-Alert Drug Checklist in ICU",
        "category": "Pharmacology",
        "tags": ["medication", "drug safety", "insulin", "heparin", "potassium", "contraindication"],
        "content": """
        HIGH-ALERT MEDICATIONS IN ICU — SAFETY CHECKLIST AND CONTRAINDICATIONS
        High-alert drugs requiring double-check verification before administration:
        1. Insulin infusions: confirm rate, concentration, and BM within 30 minutes.
        2. IV Potassium: never give >10 mmol/hr peripheral; central line for >40 mmol/hr.
        3. Heparin infusions: verify APTT target and current APTT result before changes.
        4. Vasopressors: confirm pump rate and drug concentration with second nurse.
        5. Concentrated Morphine/Opioid infusions: verify dose per body weight.
        Drug-drug interactions of note on this ward:
        - Furosemide + Gentamicin: additive ototoxicity and nephrotoxicity. Avoid.
        - Carvedilol + insulin: beta-blockade masks hypoglycaemia symptoms. Monitor BM closely.
        - Spironolactone + ACE inhibitor: risk of hyperkalaemia. Check K+ daily.
        - Metformin: HOLD in any patient with AKI, contrast exposure, or sepsis.
        Allergy cross-reactivity alerts:
        - Penicillin allergy: 10% cross-reactivity with cephalosporins. Use Azithromycin.
        - Sulfa allergy: avoid co-trimoxazole, thiazides, furosemide (partial sulfa structure).
        """,
    },
    {
        "title": "Patient Deterioration — SBAR Escalation and Rapid Response Criteria",
        "category": "General",
        "tags": ["deterioration", "SBAR", "escalation", "rapid response", "NEWS score"],
        "content": """
        PATIENT DETERIORATION — SBAR ESCALATION AND RAPID RESPONSE CRITERIA
        National Early Warning Score (NEWS2) triggers:
        Score 0-4: Monitor every 4-6 hours.
        Score 5-6 or 3 in single parameter: Urgent senior review within 30 minutes.
        Score 7+: Emergency response within 5 minutes — consider ICU referral.
        NEWS2 parameters: RR, SpO2, supplemental O2 use, BP, HR, temperature, consciousness.
        SBAR Escalation Framework:
        S (Situation): "I am calling about [patient], [location], I am concerned because..."
        B (Background): Admission diagnosis, relevant history, medications.
        A (Assessment): Current vital signs, NEWS score, trend over last hour.
        R (Recommendation): "I need you to come and review / I think this patient needs X."
        Rapid Response Team activation criteria (any one):
        - RR <6 or >30, HR <40 or >140, SBP <90 or >220.
        - SpO2 <90% on oxygen, new altered consciousness, urine output <20 mL/hr for 2h.
        - Staff member is worried about the patient even if vitals not yet critical.
        Post-arrest care: Head tilt at 30°, target normothermia, avoid hypoglycaemia.
        """,
    },
]


async def embed_text(text: str) -> list[float]:
    """Generate a 768-dimensional embedding via Gemini embedding model."""
    result = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
        ),
    )
    return result.embeddings[0].values


async def seed_sops() -> None:
    """Embed and insert all SOPs into the clinical_sops table."""
    log.info("sop_seeding_started", sop_count=len(SOPS))

    async with get_session() as session:
        # Check if already seeded
        result = await session.execute(text("SELECT COUNT(*) FROM clinical_sops"))
        count = result.scalar()
        if count >= len(SOPS):
            log.info("sop_seeding_skipped", reason="already_seeded", existing=count)
            return

        for i, sop in enumerate(SOPS):
            # Combine title + content for a richer embedding
            embed_input = f"{sop['title']}\n{sop['content'].strip()}"
            embedding = await embed_text(embed_input)

            await session.execute(
                text("""
                    INSERT INTO clinical_sops (title, category, tags, content, embedding)
                    VALUES (:title, :category, :tags, :content, :embedding)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "title":     sop["title"],
                    "category":  sop["category"],
                    "tags":      sop["tags"],
                    "content":   sop["content"].strip(),
                    "embedding": str(embedding),
                },
            )
            log.info(
                "sop_embedded_and_inserted",
                index=i + 1,
                total=len(SOPS),
                title=sop["title"],
            )

    log.info("sop_seeding_complete", total_inserted=len(SOPS))


if __name__ == "__main__":
    asyncio.run(seed_sops())