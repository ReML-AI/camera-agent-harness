#!/usr/bin/env python3
"""
Rich Student Feedback Generation

Generates eight-section professional debrief feedback using the structured
feedback schema.

Uses:
- feedback_schema.py: Pydantic models for structured feedback
- clinical_protocols.py: ABCDE, CRM, treatment protocols
- evidence_linker.py: Links feedback to source moments
- prompts/*.txt: Section-specific prompts
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.llm_client import chat, get_model

from .feedback_schema import (
    StudentFeedback,
    ScenarioDetails,
    ClinicalSkill,
    ABCDEAssessment,
    ABCDEItem,
    NonTechnicalSkills,
    NTSComponent,
    CRMReflection,
    LearningOutcomes,
    TimestampedObservation,
    Reference,
    SkillRating,
    FeedbackStatus,
    create_empty_feedback
)

from .clinical_protocols import (
    ProtocolRegistry,
    format_abcde_for_prompt,
    format_crm_for_prompt,
    format_treatment_for_prompt,
    STANDARD_REFERENCES
)

from .evidence_linker import (
    EvidenceLinker,
    EvidenceChainBuilder
)


class RichFeedbackGenerator:
    """
    Generate 8-section professional debrief feedback for students.

    Uses the configured local language model to generate evidence-based,
    timestamped feedback following the professional debrief format.
    """

    def __init__(
        self,
        model: str = None,
        prompts_dir: Optional[Path] = None
    ):
        """Initialize the feedback generator."""
        self.model = get_model(model)

        # Load prompts
        self.prompts_dir = prompts_dir or Path(__file__).parent / "prompts"
        self.prompts = self._load_prompts()

        # Load protocols
        self.protocol_registry = ProtocolRegistry()

        # Evidence linker
        self.evidence_linker = EvidenceLinker()

    def _load_prompts(self) -> Dict[str, str]:
        """Load prompt templates from files"""
        prompts = {}
        prompt_files = [
            "scenario_analysis",
            "clinical_skills",
            "abcde_assessment",
            "non_technical",
            "crm_reflection",
            "learning_outcomes"
        ]

        for name in prompt_files:
            path = self.prompts_dir / f"{name}.txt"
            if path.exists():
                with open(path, 'r') as f:
                    prompts[name] = f.read()
            else:
                print(f"Warning: Prompt file not found: {path}")
                prompts[name] = ""

        return prompts

    def generate_student_feedback(
        self,
        student_id: str,
        student_role: str,
        session_id: str,
        person_timeline: Dict,
        scenario_context: Optional[Dict] = None,
        moments_file: Optional[Path] = None,
        scenario_type: str = "General Clinical Simulation"
    ) -> StudentFeedback:
        """
        Generate complete 8-section feedback for a student.

        Args:
            student_id: Unique identifier for the student
            student_role: Role in simulation (e.g., "Student Nurse (Primary)")
            session_id: Session identifier
            person_timeline: Timeline data for this student from Stage 3
            scenario_context: Optional additional scenario context
            moments_file: Path to critical moments JSON
            scenario_type: Type of scenario (e.g., "Anaphylaxis")

        Returns:
            Complete StudentFeedback object
        """
        print(f"\n{'='*60}")
        print(f"Generating Rich Feedback for: {student_id}")
        print(f"Role: {student_role}")
        print(f"{'='*60}")

        # Load moments if file provided
        if moments_file:
            self.evidence_linker.load_moments(moments_file)

        # Create evidence builder
        evidence_builder = EvidenceChainBuilder()
        evidence_builder.linker = self.evidence_linker

        # Create base feedback structure
        feedback = create_empty_feedback(
            student_id=student_id,
            student_role=student_role,
            session_id=session_id,
            scenario_type=scenario_type
        )
        feedback.status = FeedbackStatus.AI_GENERATED
        feedback.ai_model_version = self.model

        # Generate each section
        print("\n[1/6] Generating scenario analysis...")
        feedback.scenario_details = self._generate_scenario_section(
            person_timeline, scenario_context, scenario_type
        )

        print("[2/6] Generating clinical skills assessment...")
        feedback.clinical_skills = self._generate_clinical_skills_section(
            student_id, student_role, person_timeline, scenario_type
        )

        # Generate ABCDE if applicable
        if scenario_type.lower() in ["anaphylaxis", "cardiac arrest", "sepsis", "respiratory distress"]:
            print("[2b/6] Generating ABCDE assessment...")
            feedback.abcde_assessment = self._generate_abcde_section(
                student_id, person_timeline
            )

        print("[3/6] Generating non-technical skills assessment...")
        feedback.non_technical_skills = self._generate_nts_section(
            student_id, student_role, person_timeline
        )

        print("[4/6] Generating CRM reflection...")
        feedback.crm_reflection = self._generate_crm_section(
            student_id, person_timeline
        )

        print("[5/6] Generating learning outcomes...")
        feedback.learning_outcomes = self._generate_learning_outcomes_section(
            student_id, feedback
        )

        print("[6/6] Building evidence chain...")
        # Collect all observations for evidence chain
        all_observations = self._collect_all_observations(feedback)
        feedback.evidence_chain = evidence_builder.linker.build_evidence_chain(
            all_observations
        )

        # Add references
        feedback.references = [
            Reference(citation=ref.citation, url=ref.url, protocol_name=ref.protocol_name)
            for ref in STANDARD_REFERENCES
        ]

        print(f"\n{'='*60}")
        print("Feedback generation complete!")
        print(f"  - Clinical skills assessed: {len(feedback.clinical_skills)}")
        print(f"  - Evidence links: {len(feedback.evidence_chain.evidence_links)}")
        print(f"  - References: {len(feedback.references)}")
        print(f"{'='*60}\n")

        return feedback

    def _call_local_model(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 4000
    ) -> str:
        """Call the configured local language model with a prompt."""
        if system_prompt is None:
            system_prompt = (
                "You are a clinical education expert providing constructive, "
                "evidence-based feedback for medical simulation training. "
                "Be specific, reference timestamps, and be constructive."
            )

        try:
            resp = chat(
                prompt=prompt,
                system=system_prompt,
                model=self.model,
                max_tokens=max_tokens,
            )
            return resp['text']
        except Exception as e:
            print(f"  Error calling LLM: {e}")
            return ""

    def _parse_json_response(self, response: str) -> Dict:
        """Parse JSON from a language-model response."""
        # Try to extract JSON from response
        try:
            # Look for JSON block
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON object in response
            try:
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass
        return {}

    def _generate_scenario_section(
        self,
        person_timeline: Dict,
        scenario_context: Optional[Dict],
        scenario_type: str
    ) -> ScenarioDetails:
        """Generate Section 1: Scenario Details"""
        prompt = self.prompts.get("scenario_analysis", "")

        # Build context for prompt
        moments_summary = self._summarize_moments(person_timeline)

        prompt = prompt.format(
            session_id=person_timeline.get('session_id', 'N/A'),
            scenario_type=scenario_type,
            duration_minutes=person_timeline.get('duration_minutes', 15),
            participant_count=1,
            data_sources="video, audio, vitals",
            moments_summary=moments_summary,
            vitals_summary="Vitals monitored throughout scenario"
        )

        response = self._call_local_model(prompt)
        data = self._parse_json_response(response)

        return ScenarioDetails(
            patient_presentation=data.get("patient_presentation", "Patient presenting for clinical assessment"),
            clinical_context=data.get("clinical_context", "Clinical simulation environment"),
            learning_objectives=data.get("learning_objectives", []),
            scenario_type=data.get("scenario_type", scenario_type)
        )

    def _generate_clinical_skills_section(
        self,
        student_id: str,
        student_role: str,
        person_timeline: Dict,
        scenario_type: str
    ) -> List[ClinicalSkill]:
        """Generate Section 2: Clinical Skills Assessment"""
        prompt = self.prompts.get("clinical_skills", "")

        # Get relevant protocol
        abcde_protocol = format_abcde_for_prompt(self.protocol_registry.get_abcde())
        treatment_protocol = ""
        if scenario_type.lower() == "anaphylaxis":
            anaphy = self.protocol_registry.get_treatment_protocol("anaphylaxis")
            if anaphy:
                treatment_protocol = format_treatment_for_prompt(anaphy)

        prompt = prompt.format(
            student_id=student_id,
            student_role=student_role,
            student_name=person_timeline.get('name', student_id),
            scenario_summary=f"Scenario type: {scenario_type}",
            student_moments=self._summarize_moments(person_timeline),
            abcde_protocol=abcde_protocol,
            treatment_protocol=treatment_protocol or "Standard treatment protocols apply"
        )

        response = self._call_local_model(prompt)
        data = self._parse_json_response(response)

        skills = []
        if isinstance(data, list):
            for skill_data in data:
                try:
                    skill = ClinicalSkill(
                        skill_name=skill_data.get("skill_name", "Clinical Skill"),
                        performance_rating=SkillRating(skill_data.get("performance_rating", 3)),
                        observations=[
                            TimestampedObservation(**obs)
                            for obs in skill_data.get("observations", [])
                        ],
                        protocol_reference=skill_data.get("protocol_reference"),
                        summary=skill_data.get("summary")
                    )
                    skills.append(skill)
                except Exception as e:
                    print(f"  Warning: Could not parse skill: {e}")

        # Ensure we have at least one skill
        if not skills:
            skills.append(ClinicalSkill(
                skill_name="Overall Clinical Performance",
                performance_rating=SkillRating.AVERAGE,
                summary="Clinical skills demonstrated during simulation"
            ))

        return skills

    def _generate_abcde_section(
        self,
        student_id: str,
        person_timeline: Dict
    ) -> Optional[ABCDEAssessment]:
        """Generate Section 3: ABCDE Assessment"""
        prompt = self.prompts.get("abcde_assessment", "")

        abcde_protocol = format_abcde_for_prompt(self.protocol_registry.get_abcde())

        prompt = prompt.format(
            student_id=student_id,
            student_name=person_timeline.get('name', student_id),
            scenario_summary="Clinical simulation scenario",
            student_moments=self._summarize_moments(person_timeline),
            audio_transcription=self._get_audio_transcription(person_timeline),
            abcde_protocol=abcde_protocol
        )

        response = self._call_local_model(prompt)
        data = self._parse_json_response(response)

        if not data:
            return None

        def parse_abcde_item(component_key: str, component_data: Dict) -> ABCDEItem:
            return ABCDEItem(
                component=component_key,
                status=component_data.get("status", "Not assessed"),
                actions_taken=component_data.get("actions_taken", []),
                observations=[
                    TimestampedObservation(**obs)
                    for obs in component_data.get("observations", [])
                ],
                rating=SkillRating(component_data.get("rating", 3)) if component_data.get("rating") else None,
                notes=component_data.get("notes")
            )

        return ABCDEAssessment(
            airway=parse_abcde_item("airway", data.get("airway", {})),
            breathing=parse_abcde_item("breathing", data.get("breathing", {})),
            circulation=parse_abcde_item("circulation", data.get("circulation", {})),
            disability=parse_abcde_item("disability", data.get("disability", {})),
            exposure=parse_abcde_item("exposure", data.get("exposure", {})),
            overall_sequence_followed=data.get("overall_sequence_followed", True),
            time_to_complete=data.get("time_to_complete")
        )

    def _generate_nts_section(
        self,
        student_id: str,
        student_role: str,
        person_timeline: Dict
    ) -> NonTechnicalSkills:
        """Generate Section 4: Non-Technical Skills"""
        prompt = self.prompts.get("non_technical", "")

        nts_framework = self.protocol_registry.get_nts()
        framework_text = json.dumps(
            {k: v.model_dump() for k, v in nts_framework.categories.items()},
            indent=2
        )

        prompt = prompt.format(
            student_id=student_id,
            student_role=student_role,
            student_name=person_timeline.get('name', student_id),
            scenario_summary="Clinical simulation scenario",
            audio_transcription=self._get_audio_transcription(person_timeline),
            student_moments=self._summarize_moments(person_timeline),
            nts_framework=framework_text
        )

        response = self._call_local_model(prompt)
        data = self._parse_json_response(response)

        def parse_nts_component(name: str, component_data: Dict) -> NTSComponent:
            return NTSComponent(
                skill_name=name,
                rating=SkillRating(component_data.get("rating", 3)),
                observations=[
                    TimestampedObservation(**obs)
                    for obs in component_data.get("observations", [])
                ],
                strengths=component_data.get("strengths", []),
                areas_for_improvement=component_data.get("areas_for_improvement", [])
            )

        return NonTechnicalSkills(
            communication=parse_nts_component("Communication", data.get("communication", {})),
            teamwork=parse_nts_component("Teamwork", data.get("teamwork", {})),
            leadership=parse_nts_component("Leadership", data.get("leadership", {})),
            situational_awareness=parse_nts_component("Situational Awareness", data.get("situational_awareness", {})),
            decision_making=parse_nts_component("Decision Making", data.get("decision_making", {})),
            overall_nts_rating=SkillRating(data.get("overall_nts_rating", 3)) if data.get("overall_nts_rating") else None
        )

    def _generate_crm_section(
        self,
        student_id: str,
        person_timeline: Dict
    ) -> CRMReflection:
        """Generate Section 5: CRM Reflection"""
        prompt = self.prompts.get("crm_reflection", "")

        crm_protocol = format_crm_for_prompt(self.protocol_registry.get_crm())

        prompt = prompt.format(
            student_id=student_id,
            student_role=person_timeline.get('role', 'Student'),
            student_name=person_timeline.get('name', student_id),
            scenario_summary="Clinical simulation scenario",
            student_moments=self._summarize_moments(person_timeline),
            crm_protocol=crm_protocol
        )

        response = self._call_local_model(prompt)
        data = self._parse_json_response(response)

        return CRMReflection(
            strengths=data.get("strengths", []),
            areas_for_development=data.get("areas_for_development", []),
            specific_observations=[
                TimestampedObservation(**obs)
                for obs in data.get("specific_observations", [])
            ],
            knew_environment=data.get("knew_environment"),
            mobilized_resources=data.get("mobilized_resources"),
            prevented_fixation=data.get("prevented_fixation"),
            cross_checked=data.get("cross_checked"),
            used_cognitive_aids=data.get("used_cognitive_aids"),
            re_evaluated=data.get("re_evaluated"),
            set_priorities=data.get("set_priorities")
        )

    def _generate_learning_outcomes_section(
        self,
        student_id: str,
        feedback: StudentFeedback
    ) -> LearningOutcomes:
        """Generate Section 6: Learning Outcomes"""
        prompt = self.prompts.get("learning_outcomes", "")

        # Summarize previous sections
        clinical_summary = self._summarize_clinical_skills(feedback.clinical_skills)
        nts_summary = self._summarize_nts(feedback.non_technical_skills)
        crm_summary = self._summarize_crm(feedback.crm_reflection)

        prompt = prompt.format(
            student_id=student_id,
            student_role=feedback.student_role,
            student_name=feedback.student_name or student_id,
            scenario_summary=feedback.scenario_details.clinical_context,
            clinical_skills_summary=clinical_summary,
            nts_summary=nts_summary,
            crm_summary=crm_summary,
            student_moments="See above sections for specific moments"
        )

        response = self._call_local_model(prompt)
        data = self._parse_json_response(response)

        return LearningOutcomes(
            key_achievements=data.get("key_achievements", []),
            areas_for_improvement=data.get("areas_for_improvement", []),
            recommended_focus=data.get("recommended_focus", []),
            action_plan=data.get("action_plan", []),
            debrief_summary=data.get("debrief_summary")
        )

    # Helper methods
    def _summarize_moments(self, person_timeline: Dict) -> str:
        """Summarize moments for prompts"""
        actions = person_timeline.get('actions', [])
        if not actions:
            return "No specific moments recorded"

        summary = []
        for action in actions[:20]:  # Limit to 20 for prompt length
            timestamp = action.get('timestamp_display', 'N/A')
            description = action.get('description', action.get('action', 'Unknown'))
            summary.append(f"- [{timestamp}] {description}")

        return "\n".join(summary)

    def _get_audio_transcription(self, person_timeline: Dict) -> str:
        """Get audio transcription from timeline"""
        transcriptions = []
        for action in person_timeline.get('actions', []):
            if action.get('source') == 'audio' and action.get('transcription'):
                timestamp = action.get('timestamp_display', 'N/A')
                text = action.get('transcription')
                transcriptions.append(f"[{timestamp}] {text}")

        return "\n".join(transcriptions) if transcriptions else "No audio transcription available"

    def _summarize_clinical_skills(self, skills: List[ClinicalSkill]) -> str:
        """Summarize clinical skills for prompt"""
        if not skills:
            return "No clinical skills assessed"

        summary = []
        for skill in skills:
            rating_name = skill.performance_rating.name if hasattr(skill.performance_rating, 'name') else str(skill.performance_rating)
            summary.append(f"- {skill.skill_name}: {rating_name}")
            if skill.summary:
                summary.append(f"  {skill.summary}")

        return "\n".join(summary)

    def _summarize_nts(self, nts: NonTechnicalSkills) -> str:
        """Summarize NTS for prompt"""
        components = [
            ("Communication", nts.communication),
            ("Teamwork", nts.teamwork),
            ("Leadership", nts.leadership),
            ("Situational Awareness", nts.situational_awareness),
            ("Decision Making", nts.decision_making)
        ]

        summary = []
        for name, comp in components:
            rating_name = comp.rating.name if hasattr(comp.rating, 'name') else str(comp.rating)
            summary.append(f"- {name}: {rating_name}")
            if comp.strengths:
                summary.append(f"  Strengths: {', '.join(comp.strengths[:2])}")

        return "\n".join(summary)

    def _summarize_crm(self, crm: CRMReflection) -> str:
        """Summarize CRM for prompt"""
        summary = []
        if crm.strengths:
            summary.append(f"Strengths: {', '.join(crm.strengths[:3])}")
        if crm.areas_for_development:
            summary.append(f"Areas for development: {', '.join(crm.areas_for_development[:3])}")
        return "\n".join(summary) if summary else "CRM behaviors observed"

    def _collect_all_observations(self, feedback: StudentFeedback) -> List[TimestampedObservation]:
        """Collect all observations from feedback for evidence chain"""
        observations = []

        # From clinical skills
        for skill in feedback.clinical_skills:
            observations.extend(skill.observations)

        # From NTS
        nts = feedback.non_technical_skills
        for comp in [nts.communication, nts.teamwork, nts.leadership,
                     nts.situational_awareness, nts.decision_making]:
            observations.extend(comp.observations)

        # From CRM
        observations.extend(feedback.crm_reflection.specific_observations)

        return observations


def main():
    parser = argparse.ArgumentParser(
        description="Generate rich 8-section professional debrief feedback"
    )
    parser.add_argument('--associations', type=str, required=True,
                       help="Path to moment-person associations JSON")
    parser.add_argument('--output', type=str, required=True,
                       help="Output path for feedback JSON")
    parser.add_argument('--student-id', type=str,
                       help="Generate for specific student ID only")
    parser.add_argument('--scenario-type', type=str, default="Anaphylaxis",
                       help="Scenario type (default: Anaphylaxis)")
    parser.add_argument('--session-id', type=str, default="session_001",
                       help="Session ID")
    parser.add_argument('--model', type=str, default=None,
                       help="Model identifier (default: $LLM_MODEL or qwen2.5:7b)")

    args = parser.parse_args()

    print("=" * 80)
    print("RICH STUDENT FEEDBACK GENERATION")
    print("8-Section Professional Debrief Format")
    print("=" * 80)

    # Load associations
    print(f"\nLoading associations from: {args.associations}")
    with open(args.associations, 'r') as f:
        associations_data = json.load(f)

    person_timelines = associations_data.get('person_timelines', {})
    print(f"  Loaded timelines for {len(person_timelines)} persons")

    generator = RichFeedbackGenerator(model=args.model)

    # Generate feedback
    all_feedback = []

    for person_id, timeline in person_timelines.items():
        # Filter by student ID if specified
        if args.student_id and person_id != args.student_id:
            continue

        # Skip non-student roles
        role = timeline.get('role', '')
        if 'student' not in role.lower() and 'nurse' not in role.lower():
            print(f"Skipping {person_id} (role: {role})")
            continue

        feedback = generator.generate_student_feedback(
            student_id=person_id,
            student_role=role,
            session_id=args.session_id,
            person_timeline=timeline,
            scenario_type=args.scenario_type
        )

        all_feedback.append(feedback.model_dump())

    # Save output
    output_data = {
        'session_id': args.session_id,
        'scenario_type': args.scenario_type,
        'model': generator.model,
        'generated_at': datetime.utcnow().isoformat(),
        'student_feedback': all_feedback,
        'summary': {
            'total_students': len(all_feedback)
        }
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\n{'='*80}")
    print(f"Feedback saved: {output_path}")
    print(f"Total students: {len(all_feedback)}")
    print("=" * 80)


if __name__ == "__main__":
    main()
