"""
Clinical Protocols for Professional Debrief Feedback

Provides standardized clinical protocols, assessment frameworks, and references
for generating evidence-based feedback.

Based on:
- ABCDE Assessment Framework
- Crisis Resource Management (CRM) Principles (Park et al., 2010)
- Clinical treatment protocols (Anaphylaxis, Sepsis, Cardiac Arrest, etc.)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import json
from pathlib import Path


# ============================================================================
# Protocol Types
# ============================================================================

class ProtocolType(str, Enum):
    ABCDE = "abcde"
    CRM = "crm"
    ANAPHYLAXIS = "anaphylaxis"
    SEPSIS = "sepsis"
    CARDIAC_ARREST = "cardiac_arrest"
    RESPIRATORY_DISTRESS = "respiratory_distress"


# ============================================================================
# ABCDE Assessment Protocol
# ============================================================================

class ABCDEComponent(BaseModel):
    """Single component of ABCDE assessment"""
    component: str  # A, B, C, D, or E
    name: str
    description: str
    key_assessments: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)


class ABCDEProtocol(BaseModel):
    """Complete ABCDE Assessment Protocol"""
    name: str = "ABCDE Assessment"
    description: str = "Systematic approach to patient assessment"
    components: Dict[str, ABCDEComponent] = Field(default_factory=dict)
    sequence_importance: str = "Must be followed in order A→B→C→D→E"
    reference: str = "Resuscitation Council UK Guidelines"

    @classmethod
    def get_standard_protocol(cls) -> "ABCDEProtocol":
        """Return the standard ABCDE assessment protocol"""
        return cls(
            name="ABCDE Assessment",
            description="Systematic approach to assess and treat critically ill patients",
            components={
                "airway": ABCDEComponent(
                    component="A",
                    name="Airway",
                    description="Assess airway patency and protect if compromised",
                    key_assessments=[
                        "Look for signs of airway obstruction",
                        "Listen for abnormal sounds (stridor, gurgling)",
                        "Check for tongue/lip swelling",
                        "Assess ability to speak"
                    ],
                    red_flags=[
                        "Complete airway obstruction",
                        "Stridor",
                        "Severe tongue/lip swelling",
                        "Inability to speak"
                    ],
                    interventions=[
                        "Open airway (head tilt, chin lift)",
                        "Clear visible obstructions",
                        "Consider airway adjuncts (OPA, NPA)",
                        "Call for senior help if compromise"
                    ]
                ),
                "breathing": ABCDEComponent(
                    component="B",
                    name="Breathing",
                    description="Assess respiratory function and oxygenation",
                    key_assessments=[
                        "Respiratory rate and pattern",
                        "Oxygen saturation (SpO2)",
                        "Chest expansion and symmetry",
                        "Auscultation (wheeze, crackles)",
                        "Work of breathing"
                    ],
                    red_flags=[
                        "SpO2 < 94% on air",
                        "Respiratory rate > 25 or < 8",
                        "Severe wheeze/bronchospasm",
                        "Silent chest",
                        "Cyanosis"
                    ],
                    interventions=[
                        "Administer high-flow oxygen (15L via reservoir)",
                        "Position patient upright if possible",
                        "Nebulized bronchodilators if wheeze",
                        "Prepare for assisted ventilation"
                    ]
                ),
                "circulation": ABCDEComponent(
                    component="C",
                    name="Circulation",
                    description="Assess cardiovascular status and perfusion",
                    key_assessments=[
                        "Heart rate and rhythm",
                        "Blood pressure",
                        "Capillary refill time",
                        "Skin color and temperature",
                        "ECG if available"
                    ],
                    red_flags=[
                        "Systolic BP < 90 mmHg",
                        "Heart rate > 130 or < 40",
                        "Capillary refill > 3 seconds",
                        "Cold, clammy, mottled skin",
                        "No pulse"
                    ],
                    interventions=[
                        "IV access (large bore cannula)",
                        "IV fluid bolus if hypotensive",
                        "IM Adrenaline if anaphylaxis",
                        "Cardiac monitoring",
                        "Begin CPR if no pulse"
                    ]
                ),
                "disability": ABCDEComponent(
                    component="D",
                    name="Disability",
                    description="Assess neurological status",
                    key_assessments=[
                        "Level of consciousness (AVPU or GCS)",
                        "Pupil size and reactivity",
                        "Blood glucose",
                        "Signs of seizure activity"
                    ],
                    red_flags=[
                        "GCS < 8 or rapidly falling",
                        "Unequal or fixed pupils",
                        "Hypoglycemia < 4 mmol/L",
                        "Active seizure"
                    ],
                    interventions=[
                        "Correct hypoglycemia if present",
                        "Consider recovery position",
                        "Protect airway if unconscious",
                        "Treat seizures"
                    ]
                ),
                "exposure": ABCDEComponent(
                    component="E",
                    name="Exposure",
                    description="Full examination while preventing hypothermia",
                    key_assessments=[
                        "Full body examination",
                        "Skin rash (urticaria, erythema)",
                        "Temperature",
                        "Look for triggers/causes",
                        "Check all IV sites"
                    ],
                    red_flags=[
                        "Widespread rash/urticaria",
                        "Temperature > 38.5°C or < 35°C",
                        "Signs of bleeding",
                        "Hidden injuries"
                    ],
                    interventions=[
                        "Remove allergen/trigger if identified",
                        "Maintain patient dignity",
                        "Prevent hypothermia (warm blankets)",
                        "Document findings"
                    ]
                )
            },
            sequence_importance="Always assess and treat in A→B→C→D→E order. Re-evaluate from A after any intervention.",
            reference="Resuscitation Council UK Guidelines 2021"
        )


# ============================================================================
# Crisis Resource Management (CRM) Protocol
# ============================================================================

class CRMPrinciple(BaseModel):
    """Single CRM principle"""
    name: str
    description: str
    key_behaviors: List[str] = Field(default_factory=list)
    indicators_present: List[str] = Field(default_factory=list)
    indicators_absent: List[str] = Field(default_factory=list)


class CRMProtocol(BaseModel):
    """Crisis Resource Management Protocol (Park et al., 2010)"""
    name: str = "Crisis Resource Management"
    description: str = "Non-technical skills for managing critical situations"
    principles: List[CRMPrinciple] = Field(default_factory=list)
    reference: str = "Park et al., 2010. Acquisition of critical intraoperative event management skills."

    @classmethod
    def get_standard_protocol(cls) -> "CRMProtocol":
        """Return the standard CRM protocol"""
        return cls(
            name="Crisis Resource Management",
            description="Non-technical skills for effective team performance in crisis situations",
            principles=[
                CRMPrinciple(
                    name="Know the Environment",
                    description="Knowing the environment and available resources",
                    key_behaviors=[
                        "Familiarize with equipment location",
                        "Know how to call for help",
                        "Understand available resources",
                        "Check equipment before use"
                    ],
                    indicators_present=[
                        "Quickly locates needed equipment",
                        "Knows emergency numbers/procedures",
                        "Checks equipment availability"
                    ],
                    indicators_absent=[
                        "Searching for basic equipment",
                        "Unsure how to escalate",
                        "Equipment failures due to unfamiliarity"
                    ]
                ),
                CRMPrinciple(
                    name="Mobilize Resources Early",
                    description="Mobilizing all available resources early",
                    key_behaviors=[
                        "Call for help early, not late",
                        "Involve senior staff proactively",
                        "Request additional personnel when needed",
                        "Don't wait until crisis deepens"
                    ],
                    indicators_present=[
                        "Early call for help",
                        "Proactive escalation",
                        "Team assembled quickly"
                    ],
                    indicators_absent=[
                        "Delayed escalation",
                        "Attempting to manage alone",
                        "Resources requested too late"
                    ]
                ),
                CRMPrinciple(
                    name="Prevent Fixation Errors",
                    description="Preventing and managing fixation errors",
                    key_behaviors=[
                        "Step back and reassess",
                        "Consider alternative diagnoses",
                        "Welcome input from team members",
                        "Avoid tunnel vision"
                    ],
                    indicators_present=[
                        "Considers differential diagnoses",
                        "Open to suggestions",
                        "Regular reassessment"
                    ],
                    indicators_absent=[
                        "Stuck on single diagnosis",
                        "Ignores contrary information",
                        "Repeats same failing intervention"
                    ]
                ),
                CRMPrinciple(
                    name="Cross-Check and Double-Check",
                    description="Cross-checking and double-checking medications and interventions",
                    key_behaviors=[
                        "Verify drug doses",
                        "Check expiry dates",
                        "Confirm patient identity",
                        "Use two-person verification for high-risk drugs"
                    ],
                    indicators_present=[
                        "Drug doses verified verbally",
                        "Expiry dates checked",
                        "Clear labeling of syringes"
                    ],
                    indicators_absent=[
                        "No verification of doses",
                        "Rushing medication administration",
                        "Missing safety checks"
                    ]
                ),
                CRMPrinciple(
                    name="Use Cognitive Aids",
                    description="Using cognitive aids and guidelines",
                    key_behaviors=[
                        "Reference algorithms when appropriate",
                        "Use checklists",
                        "Follow established protocols",
                        "Don't rely solely on memory"
                    ],
                    indicators_present=[
                        "Refers to protocol/algorithm",
                        "Uses checklist",
                        "Follows established guidelines"
                    ],
                    indicators_absent=[
                        "Works purely from memory",
                        "Ignores available guidelines",
                        "Ad-hoc approach to treatment"
                    ]
                ),
                CRMPrinciple(
                    name="Re-evaluate Repeatedly",
                    description="Re-evaluating the patient repeatedly (10-for-10 concept)",
                    key_behaviors=[
                        "Regular patient reassessment",
                        "Pause to review progress",
                        "10 seconds every 10 minutes to reassess",
                        "Check response to interventions"
                    ],
                    indicators_present=[
                        "Regular ABCDE reassessment",
                        "Monitors response to treatment",
                        "Pauses to review situation"
                    ],
                    indicators_absent=[
                        "No reassessment after interventions",
                        "Assumes treatment working without checking",
                        "Missing deterioration signs"
                    ]
                ),
                CRMPrinciple(
                    name="Set Priorities Dynamically",
                    description="Setting priorities dynamically and allocating attention wisely",
                    key_behaviors=[
                        "Identify most critical tasks",
                        "Delegate appropriately",
                        "Adjust priorities as situation evolves",
                        "Focus on life-threatening issues first"
                    ],
                    indicators_present=[
                        "Clear task prioritization",
                        "Effective delegation",
                        "Flexible response to changes"
                    ],
                    indicators_absent=[
                        "Distracted by minor tasks",
                        "Poor delegation",
                        "Rigid approach despite changing situation"
                    ]
                )
            ],
            reference="Park, C.S., et al., 2010. Acquisition of critical intraoperative event management skills in novice anesthesiology residents. Anesthesiology, 112(1), pp.202-211."
        )


# ============================================================================
# Non-Technical Skills (NTS) Framework
# ============================================================================

class NTSCategory(BaseModel):
    """Non-technical skill category"""
    name: str
    description: str
    elements: List[str] = Field(default_factory=list)
    positive_indicators: List[str] = Field(default_factory=list)
    negative_indicators: List[str] = Field(default_factory=list)


class NTSFramework(BaseModel):
    """Non-Technical Skills Assessment Framework"""
    name: str = "Non-Technical Skills"
    categories: Dict[str, NTSCategory] = Field(default_factory=dict)

    @classmethod
    def get_standard_framework(cls) -> "NTSFramework":
        """Return the standard NTS framework"""
        return cls(
            name="Non-Technical Skills Assessment",
            categories={
                "communication": NTSCategory(
                    name="Communication",
                    description="Verbal and non-verbal communication effectiveness",
                    elements=[
                        "Closed-loop communication",
                        "Clear and concise messaging",
                        "Active listening",
                        "Assertive communication when needed",
                        "ISBAR for handovers"
                    ],
                    positive_indicators=[
                        "Uses closed-loop communication consistently",
                        "Confirms understanding of instructions",
                        "Provides clear, structured handovers",
                        "Speaks up about concerns"
                    ],
                    negative_indicators=[
                        "Messages not acknowledged",
                        "Unclear or ambiguous instructions",
                        "Fails to confirm task completion",
                        "Avoids speaking up"
                    ]
                ),
                "teamwork": NTSCategory(
                    name="Teamwork",
                    description="Collaboration and coordination with team members",
                    elements=[
                        "Shared situational awareness",
                        "Workload distribution",
                        "Mutual support",
                        "Coordination of activities"
                    ],
                    positive_indicators=[
                        "Shares information proactively",
                        "Offers help to team members",
                        "Coordinates tasks effectively",
                        "Maintains awareness of others' workload"
                    ],
                    negative_indicators=[
                        "Works in isolation",
                        "Fails to share critical information",
                        "Does not coordinate with team",
                        "Ignores team members' struggles"
                    ]
                ),
                "leadership": NTSCategory(
                    name="Leadership",
                    description="Leading and following appropriately",
                    elements=[
                        "Clear role identification",
                        "Task allocation",
                        "Setting standards",
                        "Supporting team members"
                    ],
                    positive_indicators=[
                        "Takes charge when appropriate",
                        "Delegates tasks clearly",
                        "Provides clear direction",
                        "Adapts leadership style to situation"
                    ],
                    negative_indicators=[
                        "No clear leader identified",
                        "Unclear task allocation",
                        "Overbearing or absent leadership",
                        "Fails to establish team structure"
                    ]
                ),
                "situational_awareness": NTSCategory(
                    name="Situational Awareness",
                    description="Awareness of environment and patient status",
                    elements=[
                        "Gathering information",
                        "Recognizing and understanding",
                        "Anticipating future states",
                        "Identifying potential problems"
                    ],
                    positive_indicators=[
                        "Monitors patient continuously",
                        "Notices changes early",
                        "Anticipates potential complications",
                        "Maintains awareness despite pressure"
                    ],
                    negative_indicators=[
                        "Misses important changes",
                        "Surprised by deterioration",
                        "Tunnel vision on single issue",
                        "Loses track of time/events"
                    ]
                ),
                "decision_making": NTSCategory(
                    name="Decision Making",
                    description="Clinical reasoning and decision processes",
                    elements=[
                        "Identifying options",
                        "Assessing risks and benefits",
                        "Selecting and communicating decisions",
                        "Reviewing outcomes"
                    ],
                    positive_indicators=[
                        "Makes timely decisions",
                        "Considers alternatives",
                        "Communicates decisions clearly",
                        "Reviews and adjusts decisions"
                    ],
                    negative_indicators=[
                        "Delayed or absent decisions",
                        "Fails to consider alternatives",
                        "Decisions not communicated",
                        "Persists with failing approach"
                    ]
                )
            }
        )


# ============================================================================
# Treatment Protocols
# ============================================================================

class TreatmentStep(BaseModel):
    """Single step in a treatment protocol"""
    order: int
    action: str
    details: Optional[str] = None
    drug_dose: Optional[str] = None
    timing: Optional[str] = None


class TreatmentProtocol(BaseModel):
    """Clinical treatment protocol"""
    name: str
    condition: str
    description: str
    recognition_signs: List[str] = Field(default_factory=list)
    treatment_steps: List[TreatmentStep] = Field(default_factory=list)
    key_drugs: Dict[str, str] = Field(default_factory=dict)  # drug: dose
    references: List[str] = Field(default_factory=list)


class AnaphylaxisProtocol(TreatmentProtocol):
    """Anaphylaxis treatment protocol"""

    @classmethod
    def get_protocol(cls) -> "AnaphylaxisProtocol":
        return cls(
            name="Anaphylaxis Management",
            condition="Anaphylaxis",
            description="Emergency management of anaphylactic reaction",
            recognition_signs=[
                "Feeling of faintness or impending doom (angst)",
                "Nausea, vomiting, diarrhea",
                "Rash (urticaria or erythema)",
                "Tongue swelling",
                "Upper airway obstruction/stridor",
                "Bronchoconstriction/wheeze",
                "Hypotension (vasodilation)",
                "Tachycardia"
            ],
            treatment_steps=[
                TreatmentStep(
                    order=1,
                    action="Remove trigger",
                    details="Stop suspected drug infusion, remove allergen if identified"
                ),
                TreatmentStep(
                    order=2,
                    action="Call for help",
                    details="Early escalation is critical"
                ),
                TreatmentStep(
                    order=3,
                    action="Position patient",
                    details="Lie flat if hypotensive, do NOT sit up. Legs raised if possible"
                ),
                TreatmentStep(
                    order=4,
                    action="Airway management",
                    details="Open, clear and maintain airway"
                ),
                TreatmentStep(
                    order=5,
                    action="High-flow oxygen",
                    details="100% O2 using reservoir bag (15L/min)"
                ),
                TreatmentStep(
                    order=6,
                    action="IM Adrenaline",
                    drug_dose="0.5mg (0.5ml of 1:1000) IM into anterolateral thigh",
                    timing="Repeat every 5 minutes if no improvement"
                ),
                TreatmentStep(
                    order=7,
                    action="IV access",
                    details="Large bore cannula"
                ),
                TreatmentStep(
                    order=8,
                    action="IV fluid bolus",
                    drug_dose="10ml/kg crystalloid",
                    details="Rapid infusion for hypotension"
                ),
                TreatmentStep(
                    order=9,
                    action="Cardiac monitoring",
                    details="Connect ECG monitor"
                ),
                TreatmentStep(
                    order=10,
                    action="Bronchodilators",
                    drug_dose="Salbutamol 5mg nebulized",
                    details="If bronchospasm present"
                ),
                TreatmentStep(
                    order=11,
                    action="Antihistamine",
                    drug_dose="Chlorpheniramine 10mg IV over 2 mins",
                    details="For itch/urticaria"
                ),
                TreatmentStep(
                    order=12,
                    action="Consider CPR",
                    details="If no pulse detected, begin chest compressions"
                )
            ],
            key_drugs={
                "Adrenaline (IM)": "0.5mg (0.5ml of 1:1000) IM, repeat every 5 mins",
                "IV Fluid": "10ml/kg crystalloid bolus",
                "Salbutamol": "5mg nebulized",
                "Chlorpheniramine": "10mg IV over 2 mins",
                "Hydrocortisone": "200mg IV (consider in refractory cases)"
            },
            references=[
                "https://emed.ie/Allergy/Anaphylaxis.php",
                "IAEM Clinical Guideline 2023: Emergency Management of Anaphylaxis in Adult Patients. D Philbin, V Meighan",
                "Resuscitation Council UK Anaphylaxis Guidelines 2021"
            ]
        )


# ============================================================================
# Protocol Registry
# ============================================================================

class ProtocolRegistry:
    """Registry for accessing clinical protocols"""

    def __init__(self, protocols_dir: Optional[Path] = None):
        self.protocols_dir = protocols_dir or Path(__file__).parent.parent.parent / "data" / "protocols"
        self._protocols: Dict[str, Any] = {}
        self._load_built_in_protocols()

    def _load_built_in_protocols(self):
        """Load built-in protocols"""
        self._protocols["abcde"] = ABCDEProtocol.get_standard_protocol()
        self._protocols["crm"] = CRMProtocol.get_standard_protocol()
        self._protocols["nts"] = NTSFramework.get_standard_framework()
        self._protocols["anaphylaxis"] = AnaphylaxisProtocol.get_protocol()

    def get_protocol(self, protocol_type: str) -> Optional[Any]:
        """Get a protocol by type"""
        return self._protocols.get(protocol_type.lower())

    def get_abcde(self) -> ABCDEProtocol:
        """Get ABCDE assessment protocol"""
        return self._protocols["abcde"]

    def get_crm(self) -> CRMProtocol:
        """Get CRM protocol"""
        return self._protocols["crm"]

    def get_nts(self) -> NTSFramework:
        """Get NTS framework"""
        return self._protocols["nts"]

    def get_treatment_protocol(self, condition: str) -> Optional[TreatmentProtocol]:
        """Get treatment protocol for a specific condition"""
        return self._protocols.get(condition.lower())

    def list_protocols(self) -> List[str]:
        """List all available protocols"""
        return list(self._protocols.keys())

    def export_protocol(self, protocol_type: str) -> Optional[Dict]:
        """Export a protocol as a dictionary"""
        protocol = self.get_protocol(protocol_type)
        if protocol:
            return protocol.model_dump()
        return None

    def save_protocols_to_json(self):
        """Save all protocols to JSON files"""
        self.protocols_dir.mkdir(parents=True, exist_ok=True)

        for name, protocol in self._protocols.items():
            filepath = self.protocols_dir / f"{name}.json"
            with open(filepath, 'w') as f:
                json.dump(protocol.model_dump(), f, indent=2)


# ============================================================================
# Reference Citations
# ============================================================================

class Reference(BaseModel):
    """Clinical reference/citation"""
    id: str
    citation: str
    url: Optional[str] = None
    protocol_name: Optional[str] = None


STANDARD_REFERENCES = [
    Reference(
        id="fanning_gaba_2007",
        citation="Fanning, R.M. and Gaba, D.M., 2007. The role of debriefing in simulation-based learning. Simulation in healthcare, 2(2), pp.115-125.",
        protocol_name="Debriefing"
    ),
    Reference(
        id="emed_anaphylaxis",
        citation="Emergency Medicine Ireland - Anaphylaxis Protocol",
        url="https://emed.ie/Allergy/Anaphylaxis.php",
        protocol_name="Anaphylaxis"
    ),
    Reference(
        id="iaem_2023",
        citation="IAEM Clinical Guideline 2023: Emergency Management of Anaphylaxis in Adult Patients. D Philbin, V Meighan",
        protocol_name="Anaphylaxis"
    ),
    Reference(
        id="park_2010",
        citation="Park, C.S., Rochlen, L.R., Yaghmour, E., Higgins, N., Bauchat, J.R., Wojciechowski, K.G., Sullivan, J.T. and McCarthy, R.J., 2010. Acquisition of critical intraoperative event management skills in novice anesthesiology residents by using high-fidelity simulation-based training. Anesthesiology, 112(1), pp.202-211.",
        protocol_name="CRM"
    ),
    Reference(
        id="resus_council_2021",
        citation="Resuscitation Council UK Guidelines 2021",
        url="https://www.resus.org.uk/library/2021-resuscitation-guidelines",
        protocol_name="ABCDE"
    )
]


def get_references_for_protocol(protocol_name: str) -> List[Reference]:
    """Get relevant references for a specific protocol"""
    return [ref for ref in STANDARD_REFERENCES if ref.protocol_name == protocol_name or ref.protocol_name is None]


# ============================================================================
# Helper Functions
# ============================================================================

def format_abcde_for_prompt(protocol: ABCDEProtocol) -> str:
    """Format ABCDE protocol for inclusion in AI prompts"""
    lines = ["ABCDE Assessment Framework:", ""]
    for key, component in protocol.components.items():
        lines.append(f"**{component.component} - {component.name}**")
        lines.append(f"  Description: {component.description}")
        lines.append("  Key Assessments:")
        for assessment in component.key_assessments:
            lines.append(f"    - {assessment}")
        lines.append("  Red Flags:")
        for flag in component.red_flags:
            lines.append(f"    - {flag}")
        lines.append("")
    return "\n".join(lines)


def format_crm_for_prompt(protocol: CRMProtocol) -> str:
    """Format CRM protocol for inclusion in AI prompts"""
    lines = ["Crisis Resource Management (CRM) Principles:", ""]
    for principle in protocol.principles:
        lines.append(f"**{principle.name}**")
        lines.append(f"  {principle.description}")
        lines.append("  Key Behaviors:")
        for behavior in principle.key_behaviors:
            lines.append(f"    - {behavior}")
        lines.append("")
    return "\n".join(lines)


def format_treatment_for_prompt(protocol: TreatmentProtocol) -> str:
    """Format treatment protocol for inclusion in AI prompts"""
    lines = [f"{protocol.name}:", ""]
    lines.append("Recognition Signs:")
    for sign in protocol.recognition_signs:
        lines.append(f"  - {sign}")
    lines.append("")
    lines.append("Treatment Steps:")
    for step in protocol.treatment_steps:
        line = f"  {step.order}. {step.action}"
        if step.drug_dose:
            line += f" ({step.drug_dose})"
        if step.details:
            line += f" - {step.details}"
        lines.append(line)
    return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    # Demo: Print protocols
    registry = ProtocolRegistry()

    print("Available protocols:", registry.list_protocols())
    print("\n" + "="*80)

    # Print ABCDE
    abcde = registry.get_abcde()
    print(format_abcde_for_prompt(abcde))
    print("="*80)

    # Print CRM
    crm = registry.get_crm()
    print(format_crm_for_prompt(crm))
    print("="*80)

    # Print Anaphylaxis
    anaphy = registry.get_treatment_protocol("anaphylaxis")
    if anaphy:
        print(format_treatment_for_prompt(anaphy))

    # Save to JSON
    registry.save_protocols_to_json()
    print(f"\nProtocols saved to: {registry.protocols_dir}")
