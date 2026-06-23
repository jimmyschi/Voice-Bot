# Athena Agent Bug Report

Generated: 2026-06-23 13:08 UTC
Total calls analyzed: (see transcripts/)
Total issues found: **13**

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 6 |
| Medium | 5 |
| Low | 0 |

---

## Bug 1: Contradictory responses about practice type cause patient confusion

**Severity:** CRITICAL  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `00:49` in transcript

**Agent said:**
> yes.

**Expected behaviour:**
When the patient asked 'Is this not a general medical office?', the agent should have clearly and immediately stated: 'No, Pivot Point Orthopedics is a specialist orthopedics practice, not a general medical office. We would not be able to schedule a routine physical exam here.'

**Details:**
The agent answered 'yes' when the patient directly asked if this was a general medical office, which is factually incorrect — it is an orthopedics specialist practice. This directly contradicts the correct information provided moments later at 01:01, causing the patient unnecessary confusion and wasting time. Providing false confirmation of a factual question about practice type is a significant factual error.

---

## Bug 2: Factual error — confirmed being a general medical office when it is not

**Severity:** CRITICAL  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `00:49` in transcript

**Agent said:**
> yes.

**Expected behaviour:**
The agent should have responded: 'No, Pivot Point Orthopedics is a specialist orthopedics practice, not a general medical office. We are unable to schedule routine physical exams here.'

**Details:**
Confirming to a patient that an orthopedics specialist office is a 'general medical office' is a direct factual error. This misinformation could lead a patient to believe they are booking a physical exam when they are not, or waste significant time before the error is corrected. In a healthcare context, inaccurate information about the nature of the practice is a serious issue.

---

## Bug 3: Incoherent greeting / fragmented opening statement

**Severity:** HIGH  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `00:16` in transcript

**Agent said:**
> For calling Pivot.

**Expected behaviour:**
The agent should deliver a complete, coherent greeting such as 'Thank you for calling Pivot Point Orthopedics. How can I help you today?'

**Details:**
The agent's first substantive response is a sentence fragment that makes no grammatical or contextual sense. This creates immediate confusion for the patient and reflects poorly on the professionalism of the practice. A proper greeting is a fundamental requirement of a phone agent.

---

## Bug 4: Failure to redirect or assist patient who dialled the wrong office

**Severity:** HIGH  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `01:27` in transcript

**Agent said:**
> No worries at all. If you need anything related to orthopedics,

**Expected behaviour:**
Once it was clear the patient needed a general practice, the agent should have acknowledged the misdial empathetically, confirmed it cannot help with a physical exam, and ideally offered to provide a referral number or suggest the patient contact their primary care provider or insurance company for the correct number.

**Details:**
The agent's final substantive response is an incomplete sentence that only offers orthopedics-related help, which the patient had already explicitly said they do not need. The agent made no effort to assist the patient in finding the right resource, which is an unhelpful and dismissive conclusion to the interaction. Even a simple suggestion to search for a primary care provider would have been more appropriate.

---

## Bug 5: Multiple incomplete/truncated sentences throughout the conversation

**Severity:** HIGH  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `01:16` in transcript

**Agent said:**
> Just to clarify,

**Expected behaviour:**
The agent should complete its sentences and deliver full, coherent responses. For example: 'Just to clarify, Pivot Point Orthopedics is a specialist practice focused on musculoskeletal conditions and cannot schedule routine physical exams.'

**Details:**
On multiple occasions (00:35, 01:16, 01:27) the agent begins a sentence and does not complete it, leaving the patient waiting and confused. This pattern of truncated responses suggests a systemic issue with the agent's response generation or turn-taking logic. Incomplete utterances severely degrade the patient experience and make the agent appear broken or unreliable.

---

## Bug 6: Agent Unaware of Current Date — Presents June Dates Without Explanation

**Severity:** HIGH  
**Call:** CAa1da0eb47194790749c0e89702a2a0ba — scenario `simple_scheduling`  
**Location:** `01:41` in transcript

**Agent said:**
> On Monday, June 29, you can see

**Expected behaviour:**
Before presenting appointment dates, the agent should either be aware of the current date or proactively confirm/state it to the patient to avoid confusion, e.g. 'Just to confirm, today is June 23rd, so next week begins June 29th. On Monday June 29th, you can see...'

**Details:**
The agent offered a June date without first clarifying or confirming the current date, which caused significant patient confusion when they believed the current date was March 15th. This suggests the agent lacked situational awareness about the actual date context it was operating in. A proactive date clarification at the outset of availability-checking would have prevented two full turns of confusion and back-and-forth.

---

## Bug 7: Missing Patient Name Collection

**Severity:** HIGH  
**Call:** CAa1da0eb47194790749c0e89702a2a0ba — scenario `simple_scheduling`  
**Location:** `00:20` in transcript

**Agent said:**
> I just need to confirm your date of birth. Could you please provide your date of birth?

**Expected behaviour:**
The agent should collect the patient's full name in addition to date of birth before proceeding to scheduling, as name is a required field to look up and identify the patient record.

**Details:**
The agent only collected date of birth to identify the patient and explicitly stated 'That's all I need for now,' without ever asking for the patient's name. Date of birth alone is insufficient to uniquely identify a patient in most EHR systems. Skipping name collection is a missing information collection failure that could result in booking the appointment against the wrong patient record.

---

## Bug 8: Scheduling Task Left Incomplete at End of Call

**Severity:** HIGH  
**Call:** CAa1da0eb47194790749c0e89702a2a0ba — scenario `simple_scheduling`  
**Location:** `02:17` in transcript

**Agent said:**
> today is actually June today is June 23.

**Expected behaviour:**
After confirming the date and the patient's acceptance of June 29th, the agent should immediately proceed to present available time slots for that day and complete the booking.

**Details:**
At the end of the transcript, the patient has confirmed interest in Monday June 29th and asked for available time slots, but the agent's last action was only correcting the date confusion. The appointment was never actually scheduled, meaning the core task of the call — booking an annual physical exam — remained incomplete. This represents a significant unhelpfulness failure for what should be a straightforward scheduling interaction.

---

## Bug 9: Premature date-of-birth collection before confirming practice identity

**Severity:** MEDIUM  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `00:26` in transcript

**Agent said:**
> Can you please provide your date of birth?

**Expected behaviour:**
Before collecting any personal information, the agent should first identify the practice clearly and confirm whether it can help with the patient's stated need (a routine physical exam), especially since the patient had not yet been told this is an orthopedics office.

**Details:**
The agent skips identifying the practice and jumps straight to collecting a sensitive data point (date of birth) without establishing context or relevance. This is premature and potentially confusing, as the patient did not yet know they had reached a specialist orthopedics office. Collecting PHI before confirming the patient is even in the right place is poor practice.

---

## Bug 10: Failure to collect patient name at any point

**Severity:** MEDIUM  
**Call:** CA92dcd32ad9b9b07b4673c5c483c827bf — scenario `simple_scheduling`  
**Location:** `` in transcript

**Agent said:**
> Can you please provide your date of birth?

**Expected behaviour:**
The agent should collect the patient's full name as a minimum identifier before or alongside date of birth, particularly if attempting to look up a patient record.

**Details:**
Throughout the entire conversation the agent never asked for the patient's name, which is a standard required field for any patient interaction. While this call ultimately could not be scheduled (wrong office), the agent's information-collection process was incomplete from the outset. This represents a gap in required field collection that would be problematic in any valid scheduling scenario.

---

## Bug 11: Truncated/Split Response Across Patient Interruption

**Severity:** MEDIUM  
**Call:** CAa1da0eb47194790749c0e89702a2a0ba — scenario `simple_scheduling`  
**Location:** `01:12` in transcript

**Agent said:**
> Let me check for any provider's availability for your

**Expected behaviour:**
The agent should deliver a complete, coherent sentence before the patient has an opportunity to respond, e.g. 'Let me check availability for your annual physical exam next week. One moment.'

**Details:**
The agent's response was split across two turns ('Let me check for any provider's availability for your' at 01:12 and 'annual physical exam next week. One moment.' at 01:22), creating a fragmented and confusing interaction. This appears to be a speech synthesis or turn-management failure that breaks conversational flow. In a healthcare context, broken or incomplete sentences can erode patient trust and confidence in the system.

---

## Bug 12: Delayed and Hesitant Date Correction

**Severity:** MEDIUM  
**Call:** CAa1da0eb47194790749c0e89702a2a0ba — scenario `simple_scheduling`  
**Location:** `02:16` in transcript

**Agent said:**
> today is actually June today is June 23.

**Expected behaviour:**
The agent should clearly and confidently state the current date the first time the patient expressed confusion, e.g. 'I apologize for any confusion — today is June 23rd, so next week would be the week of June 29th.'

**Details:**
When the patient expressed confusion about the dates being in June, the agent failed to immediately and clearly clarify the current date on the first challenge (01:56), instead repeating another June date ('On Monday, June 20'). When the correction finally came at 02:16, it was delivered haltingly with a false start ('today is actually June today is June 23'), which undermines confidence in the agent. A prompt, clear correction would have resolved the confusion one turn earlier.

---

## Bug 13: Incomplete Sentence — Response Cuts Off Mid-Presentation of Availability

**Severity:** MEDIUM  
**Call:** CAa1da0eb47194790749c0e89702a2a0ba — scenario `simple_scheduling`  
**Location:** `01:41` in transcript

**Agent said:**
> On Monday, June 29, you can see

**Expected behaviour:**
The agent should complete the full availability slot information including the provider name and time options before yielding the floor, e.g. 'On Monday, June 29, you can see Dr. Smith at 9:00 AM or 2:00 PM.'

**Details:**
The agent's sentence was interrupted mid-delivery at 01:41, leaving out the provider name and available time slots. While a patient interruption contributed to this, the agent did not recover by completing the sentence or re-presenting the full information once the patient's confusion was resolved. By the end of the transcript the patient is still waiting to hear what time slots are available on June 29th, leaving the core scheduling task unresolved.

---
