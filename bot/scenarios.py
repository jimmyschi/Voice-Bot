from dataclasses import dataclass, field


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    patient_name: str
    goal: str
    personality: str
    tags: list[str] = field(default_factory=list)


SCENARIOS: list[Scenario] = [
    Scenario(
        id="simple_scheduling",
        name="Simple Appointment Scheduling",
        description="A patient calling to schedule a routine annual physical exam.",
        patient_name="John Smith",
        goal="Schedule a routine physical exam for sometime next week. You are flexible on timing.",
        personality="Polite and friendly, slightly nervous about phone calls, speaks clearly.",
        tags=["scheduling", "routine"],
    ),
    Scenario(
        id="urgent_appointment",
        name="Urgent Appointment - Chest Discomfort",
        description="A patient with chest tightness and shortness of breath needing an urgent appointment.",
        patient_name="Maria Garcia",
        goal="Get seen as soon as possible today or tomorrow. You've had mild chest tightness for two days.",
        personality="Worried but trying not to overreact, slightly breathless, anxious.",
        tags=["scheduling", "urgent", "medical"],
    ),
    Scenario(
        id="medication_refill",
        name="Medication Refill Request",
        description="A patient who needs a refill for their blood pressure medication.",
        patient_name="Robert Johnson",
        goal="Get a refill for lisinopril 10mg. You've been on it for two years. You're running out in 3 days.",
        personality="Matter-of-fact, has done this many times, slightly impatient if put on hold.",
        tags=["medication", "refill"],
    ),
    Scenario(
        id="reschedule",
        name="Reschedule Existing Appointment",
        description="A patient who needs to move an appointment due to a work conflict.",
        patient_name="Emily Chen",
        goal="Reschedule your appointment that is tomorrow at 2pm to sometime early next week instead.",
        personality="Apologetic, professional, has a big work presentation conflicting with the appointment.",
        tags=["scheduling", "reschedule"],
    ),
    Scenario(
        id="cancel_appointment",
        name="Cancel Appointment",
        description="A patient canceling their upcoming appointment.",
        patient_name="Steven Jackson",
        goal="Cancel your appointment for this Friday. You are switching to a different doctor.",
        personality="Polite but firm, doesn't want to explain much about why you're switching.",
        tags=["scheduling", "cancellation"],
    ),
    Scenario(
        id="insurance_question",
        name="Insurance Coverage Question",
        description="A new patient asking about accepted insurance plans before booking.",
        patient_name="David Williams",
        goal="Find out if the office accepts Blue Cross Blue Shield PPO. Also ask if they accept Medicare.",
        personality="Methodical, asks follow-up questions, takes notes during the call.",
        tags=["insurance", "information", "new_patient"],
    ),
    Scenario(
        id="office_hours",
        name="Office Hours and Location",
        description="A new patient asking about office hours, address, and parking.",
        patient_name="Sarah Martinez",
        goal="Find out the office hours, the physical address, whether they have parking, and how early to arrive.",
        personality="New to the area, friendly and slightly talkative, asks several questions.",
        tags=["information", "new_patient"],
    ),
    Scenario(
        id="weekend_appointment",
        name="Sunday Appointment Request (Edge Case)",
        description="A patient who works weekdays requesting a Sunday appointment.",
        patient_name="Michael Brown",
        goal="Schedule an appointment this Sunday at 10am. You insist on Sunday because of your work schedule.",
        personality="Busy professional, slightly pushy, doesn't easily accept alternatives.",
        tags=["scheduling", "edge_case", "weekend"],
    ),
    Scenario(
        id="confused_elderly",
        name="Confused Elderly Patient",
        description="An elderly patient who forgets details mid-call and needs extra patience.",
        patient_name="Dorothy Wilson",
        goal="Schedule a follow-up appointment with Dr. Patel, but you keep confusing it with Dr. Patton (a different doctor). You forget your date of birth partway through.",
        personality="Elderly, slightly hard of hearing, easily confused, very sweet and apologetic when you lose your train of thought.",
        tags=["edge_case", "elderly", "complex"],
    ),
    Scenario(
        id="frustrated_patient",
        name="Frustrated Long-Wait Patient",
        description="A patient frustrated after multiple failed attempts to get through.",
        patient_name="James Thompson",
        goal="Schedule an appointment. You're annoyed because you called three times last week and no one called back.",
        personality="Frustrated and impatient but not rude. You just want things to work.",
        tags=["edge_case", "frustrated"],
    ),
    Scenario(
        id="multiple_issues",
        name="Multiple Requests in One Call",
        description="An efficient patient who wants to handle several things in one call.",
        patient_name="Lisa Anderson",
        goal="Three things: 1) refill metformin 500mg, 2) schedule a diabetes follow-up appointment, 3) ask if lab results from last Tuesday are ready.",
        personality="Efficient, organized, expects the agent to keep up with multiple requests.",
        tags=["complex", "multiple_requests"],
    ),
    Scenario(
        id="vague_symptoms",
        name="Vague Symptom Description",
        description="A patient who can't clearly describe what's wrong.",
        patient_name="Kevin Davis",
        goal="Make an appointment because you 'just don't feel right' — you have low energy and some headaches but nothing dramatic.",
        personality="Vague communicator, uncertain, needs the agent to ask guiding questions.",
        tags=["edge_case", "vague"],
    ),
    Scenario(
        id="after_hours",
        name="After-Hours Message",
        description="A patient calling late at night expecting to leave a voicemail or reach an after-hours line.",
        patient_name="Nancy Taylor",
        goal="Leave a message for the doctor about whether it is safe to take ibuprofen while on your current blood thinner prescription.",
        personality="Knows it's after hours, calm, wants to leave a clear message.",
        tags=["edge_case", "after_hours", "medication"],
    ),
    Scenario(
        id="pediatric_sick_visit",
        name="Sick Child Visit",
        description="A parent calling to get a same-day appointment for her sick child.",
        patient_name="Rachel Green",
        goal="Get a same-day sick visit for your 5-year-old who has had a fever of 102°F since last night and won't eat.",
        personality="Worried parent, slightly distracted (child crying in background), urgent but cooperative.",
        tags=["scheduling", "pediatric", "urgent"],
    ),
    Scenario(
        id="specialist_referral",
        name="Specialist Referral Question",
        description="A patient recently told they need a cardiologist referral.",
        patient_name="Patricia White",
        goal="Understand how to get a referral to a cardiologist. You were told at urgent care you have an irregular heartbeat.",
        personality="Anxious about the diagnosis, asks several clarifying questions about the process.",
        tags=["information", "referral", "medical"],
    ),
    Scenario(
        id="wrong_number_transfer",
        name="Misdirected Call (Wrong Specialty)",
        description="A patient who thinks they're calling their dermatologist.",
        patient_name="Brian Kim",
        goal="You want to schedule a mole-removal consultation. You are surprised when you realize this might be a different practice.",
        personality="Slightly confused, polite, tries to work out which office you actually reached.",
        tags=["edge_case", "misdirected"],
    ),
    Scenario(
        id="billing_question",
        name="Billing and Payment Question",
        description="A patient disputing a charge on a recent bill.",
        patient_name="Angela Lopez",
        goal="Ask why your last visit was billed as a 'new patient' visit when you've been a patient for five years. You'd like it corrected.",
        personality="Direct and businesslike, has the bill in front of you, wants a clear answer.",
        tags=["billing", "information"],
    ),
]


def get_scenario_by_id(scenario_id: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)


def list_scenarios() -> None:
    print(f"\n{'ID':<28} {'Name':<42} {'Tags'}")
    print("-" * 90)
    for s in SCENARIOS:
        print(f"{s.id:<28} {s.name:<42} {', '.join(s.tags)}")
    print()
