"""
Slide Generator Service — Unified

Generates presentation slides for both session-level (moments/evaluations)
and student-level (rich feedback) debrief presentations.

This is the single server-side source of truth for slide generation.
The frontend should call the API rather than generating slides locally.
"""
from typing import List, Dict, Any, Optional
import json


# =============================================================================
# Shared Helpers
# =============================================================================

def _safe_text(value, fallback=""):
    """Return value as string, never None."""
    if value is None:
        return fallback
    return str(value)


def _format_time(seconds):
    """Format seconds as M:SS."""
    if seconds is None:
        return "0:00"
    seconds = float(seconds)
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to Xm Ys."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"


def _format_student_id(student_id: str) -> str:
    """Format student_id into readable name: 'cam1_person_1' -> 'Cam1 Person 1'."""
    if not student_id:
        return "Student"
    return student_id.replace("_", " ").title()


def _filter_transcript_for_moment(transcript, start_time, end_time, max_segments=2):
    """Filter transcript segments that overlap with a moment's time window."""
    if not transcript:
        return []
    segments = []
    for seg in transcript:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', seg_start)
        if seg_start >= start_time and seg_end <= end_time:
            segments.append({
                'speaker': seg.get('speaker', ''),
                'text': seg.get('text', ''),
                'start': seg_start,
                'end': seg_end,
            })
        if len(segments) >= max_segments:
            break
    return segments


def _find_highest_severity_moment(moments):
    """Find the moment with highest severity + confidence for Pause & Reflect placement."""
    if not moments:
        return None
    best = None
    best_score = -1
    for m in moments:
        severity = m.get('severity', 'warning')
        confidence = m.get('confidence', 0.5)
        score = (2.0 if severity == 'critical' else 1.0) * confidence
        if score > best_score:
            best_score = score
            best = m
    return best


def _extract_observations_from_moment(moment):
    """Extract key observation strings from a moment's sources."""
    key_observations = []
    sources = moment.get("sources", {})

    if isinstance(sources, dict):
        for source_key, source_data in sources.items():
            if isinstance(source_data, dict) and source_data.get("detected"):
                data_items = source_data.get("data", [])
                for item in data_items:
                    if isinstance(item, dict):
                        if "description" in item:
                            key_observations.append(f"[{source_key}] {item['description']}")
                        elif "text" in item:
                            text = item["text"][:100]
                            key_observations.append(f"[{source_key}] {text}")
                        elif "anomalies" in item:
                            for anomaly in item["anomalies"]:
                                reason = anomaly.get("reason", "")
                                if reason:
                                    key_observations.append(f"[{source_key}] {reason}")

    if not key_observations:
        summary = moment.get("summary", "")
        if summary:
            parts = summary.replace("[", "\n[").split("\n")
            key_observations = [p.strip() for p in parts if p.strip()][:4]

    if not key_observations and moment.get("summary"):
        key_observations.append(moment.get("summary"))

    return key_observations[:6]


def _generate_key_takeaways(moments, evaluations):
    """Generate key takeaways from the session."""
    takeaways = []
    evaluated_count = 0
    positive_count = 0
    improvement_count = 0
    learning_count = 0

    for eval_data in evaluations:
        student_feedback = eval_data.get("student_feedback", {})
        has_feedback = (
            student_feedback.get("positive") or
            student_feedback.get("negative") or
            student_feedback.get("learningPoints")
        )
        if has_feedback:
            evaluated_count += 1
            if student_feedback.get("positive"):
                positive_count += 1
            if student_feedback.get("negative"):
                improvement_count += 1
            if student_feedback.get("learningPoints"):
                learning_count += 1

    if evaluated_count > 0:
        takeaways.append(f"{evaluated_count} critical moment{'s' if evaluated_count != 1 else ''} evaluated with personalized feedback")
    if positive_count > 0:
        takeaways.append(f"{positive_count} area{'s' if positive_count != 1 else ''} of strong performance recognized")
    if improvement_count > 0:
        takeaways.append(f"{improvement_count} opportunity/opportunities for growth identified")
    if learning_count > 0:
        takeaways.append(f"{learning_count} key learning point{'s' if learning_count != 1 else ''} for follow-up")

    if not takeaways:
        takeaways.append("Session review in progress - complete evaluations to generate takeaways")

    return takeaways[:4]


# =============================================================================
# Moment Slide Generators (shared between session-level and student-level)
# =============================================================================

def _generate_timeline_slide(moments, slide_index):
    """Generate a timeline overview slide from moments."""
    if not moments:
        return None, slide_index

    moment_summaries = []
    for m in moments:
        moment_summaries.append({
            'id': m.get('id', '?'),
            'start_time': m.get('start_time', 0),
            'end_time': m.get('end_time', 0),
            'severity': m.get('severity', 'warning'),
            'summary': _safe_text(m.get('summary', ''))[:60],
        })

    slide = {
        "slide_number": slide_index,
        "type": "timeline",
        "title": "Session Timeline",
        "content": {
            "moments": moment_summaries,
        },
        "presenter_notes": "Select which moments to focus on. You can skip less critical ones.",
        "duration_suggestion": 30,
    }
    return slide, slide_index + 1


def _generate_moment_slides(moments, evaluations, transcript, slide_index):
    """
    Generate evidence + feedback slide pairs for each moment.
    Inserts a pause_reflect slide after the highest-severity moment's evidence.
    Returns list of slides and the next slide_index.
    """
    slides = []
    eval_lookup = {e.get("moment_id"): e for e in (evaluations or [])}
    highest_severity_moment = _find_highest_severity_moment(moments)
    pause_reflect_inserted = False

    # Cap at 10 moments if >12 exist (plan Section 7: max ~35 slides)
    display_moments = moments
    extra_count = 0
    if len(moments) > 12:
        # Sort by severity (critical first) then confidence, take top 10
        scored = sorted(
            moments,
            key=lambda m: (
                2.0 if m.get('severity') == 'critical' else 1.0,
                m.get('confidence', 0.5),
            ),
            reverse=True,
        )
        display_moments = scored[:10]
        extra_count = len(moments) - 10

    for moment in display_moments:
        moment_id = moment.get("id")
        eval_data = eval_lookup.get(moment_id, {})

        # Skip if explicitly marked as not relevant
        if eval_data.get("moment_relevant") is False:
            continue

        start_time = moment.get("start_time", 0)
        end_time = moment.get("end_time", 0)
        duration = end_time - start_time
        clip_duration = min(30, duration)
        clip_start = start_time
        clip_end = start_time + clip_duration

        video_clip = {
            "start": clip_start,
            "end": clip_end,
            "duration": clip_duration,
            "cameras": ["cam1", "cam2", "cam3", "monitor"],
        }

        key_observations = _extract_observations_from_moment(moment)
        transcript_snippets = _filter_transcript_for_moment(
            transcript, start_time, end_time
        )
        severity = moment.get("severity", "warning")
        clinical_sig = eval_data.get("edited_description") or moment.get("clinical_significance", "")

        # --- Evidence Slide ---
        evidence_slide = {
            "slide_number": slide_index,
            "type": "moment_evidence",
            "moment_id": moment_id,
            "title": f"Critical Moment #{moment_id}",
            "subtitle": f"{moment.get('start_time_formatted', '')} ({format_duration(duration)})",
            "severity": severity,
            "video_clip": video_clip,
            "key_observations": key_observations,
            "transcript_snippets": transcript_snippets,
            "presenter_notes": "Ask: 'What do you think happened here?' before advancing to the feedback slide.",
            "duration_suggestion": 60,
        }
        slides.append(evidence_slide)
        slide_index += 1

        # --- Pause & Reflect (after highest-severity moment's evidence) ---
        if (not pause_reflect_inserted and highest_severity_moment
                and moment.get("id") == highest_severity_moment.get("id")):
            pause_slide = _generate_pause_reflect_slide(moment, eval_data, slide_index)
            if pause_slide:
                slides.append(pause_slide)
                slide_index += 1
                pause_reflect_inserted = True

        # --- Feedback Slide ---
        feedback = eval_data.get("student_feedback", {})
        positive = feedback.get("positive", "")
        negative = feedback.get("negative", "")
        learning_points = feedback.get("learningPoints", "")

        has_feedback = any([positive, negative, learning_points, clinical_sig])

        if has_feedback:
            feedback_slide = {
                "slide_number": slide_index,
                "type": "moment_feedback",
                "moment_id": moment_id,
                "title": f"Feedback — Moment #{moment_id}",
                "severity": severity,
                "video_clip": video_clip,
                "presenter_notes": {
                    "clinical_significance": clinical_sig or None,
                    "positive_feedback": positive or None,
                    "areas_for_improvement": negative or None,
                    "learning_points": learning_points or None,
                },
                "duration_suggestion": 120,
            }
            slides.append(feedback_slide)
            slide_index += 1

    # Add note if moments were capped
    if extra_count > 0:
        slides.append({
            "slide_number": slide_index,
            "type": "moment_feedback",
            "moment_id": None,
            "title": f"Additional Moments ({extra_count} not shown)",
            "severity": "warning",
            "video_clip": {},
            "presenter_notes": {
                "clinical_significance": f"{extra_count} additional moments were detected but not included in this presentation. Review the full session recording for complete coverage.",
                "positive_feedback": None,
                "areas_for_improvement": None,
                "learning_points": None,
            },
            "duration_suggestion": 30,
        })
        slide_index += 1

    return slides, slide_index


def _generate_pause_reflect_slide(moment, eval_data, slide_index):
    """Generate a Pause & Reflect slide based on the moment context."""
    # Try to derive options from available data
    options = []
    clinical_sig = eval_data.get("edited_description") or moment.get("clinical_significance", "")

    # Use generic reflective prompts
    question = "What would you do differently?"
    if clinical_sig:
        question = "Considering this situation, what would you do differently?"

    options = [
        "What went well?",
        "What would you change?",
        "What will you take forward?",
    ]

    return {
        "slide_number": slide_index,
        "type": "pause_reflect",
        "title": "Pause & Reflect",
        "content": {
            "question": question,
            "options": options,
        },
        "presenter_notes": "Allow 2-3 minutes for open discussion before advancing.",
        "duration_suggestion": 180,
    }


# =============================================================================
# Session-Level Slide Generation (backward compatible)
# =============================================================================

def generate_presentation_slides(
    session_id: str,
    moments: List[Dict[str, Any]],
    evaluations: List[Dict[str, Any]],
    student_name: str = "Student",
    evaluator_name: str = "Evaluator",
    transcript: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate session-level presentation slides from evaluated moments.

    This is the original session-level flow: Title → Timeline → Moment pairs → Summary.
    For the full student-level deck, use generate_student_presentation_slides().

    Args:
        session_id: Session identifier
        moments: List of critical moment data
        evaluations: List of doctor evaluations
        student_name: Name of the student
        evaluator_name: Name of the evaluator
        transcript: Optional transcript segments for the session

    Returns:
        List of slide objects
    """
    slides = []
    slide_num = 1

    # 1. Title slide
    slides.append({
        "type": "title",
        "slide_number": slide_num,
        "title": "Clinical Simulation Debrief",
        "subtitle": f"Session: {session_id}",
        "metadata": {
            "student": student_name,
            "evaluator": evaluator_name,
            "total_moments": len(moments),
        },
    })
    slide_num += 1

    # 2. Create evaluation lookup
    eval_lookup = {eval.get("moment_id"): eval for eval in evaluations}

    # 3. Generate slides for each moment (type: "moment" for frontend compat)
    for moment in moments:
        moment_id = moment.get("id")
        eval_data = eval_lookup.get(moment_id, {})

        # Skip if moment was explicitly marked as not relevant
        if eval_data.get("moment_relevant") is False:
            continue

        start_time = moment.get("start_time", 0)
        end_time = moment.get("end_time", 0)
        duration = end_time - start_time
        clip_duration = min(30, duration)
        clip_start = start_time
        clip_end = start_time + clip_duration

        # Extract feedback
        student_feedback = eval_data.get("student_feedback", {})
        positive = student_feedback.get("positive", "")
        negative = student_feedback.get("negative", "")
        learning_points = student_feedback.get("learningPoints", "")

        # Build key observations from sources
        key_observations = _extract_observations_from_moment(moment)

        # Add clinical significance
        clinical_sig = eval_data.get("edited_description") or moment.get("clinical_significance", "")

        # Transcript snippets
        transcript_snippets = _filter_transcript_for_moment(
            transcript, start_time, end_time
        ) if transcript else []

        slides.append({
            "type": "moment",
            "slide_number": slide_num,
            "moment_id": moment_id,
            "title": f"Critical Moment #{moment_id}",
            "subtitle": f"{moment.get('start_time_formatted', '')} ({format_duration(duration)})",
            "severity": moment.get("severity", "warning"),
            "video_clip": {
                "start": clip_start,
                "end": clip_end,
                "duration": clip_duration,
                "cameras": ["cam1", "cam2", "cam3", "monitor"],
            },
            "key_observations": key_observations,
            "transcript_snippets": transcript_snippets,
            "presenter_notes": {
                "positive_feedback": positive if positive else None,
                "areas_for_improvement": negative if negative else None,
                "learning_points": learning_points if learning_points else None,
                "clinical_significance": clinical_sig if clinical_sig else None,
            },
        })
        slide_num += 1

    # 4. Summary slide
    if len(slides) > 1:
        relevant_count = len(slides) - 1  # Exclude title slide
        evaluated_count = sum(
            1 for e in evaluations
            if e.get("student_feedback", {}).get("positive")
            or e.get("student_feedback", {}).get("negative")
            or e.get("student_feedback", {}).get("learningPoints")
        )

        slides.append({
            "type": "summary",
            "slide_number": slide_num,
            "title": "Session Summary",
            "content": {
                "total_moments_reviewed": relevant_count,
                "total_moments_evaluated": evaluated_count,
                "session_id": session_id,
                "student": student_name,
                "evaluator": evaluator_name,
            },
            "key_takeaways": _generate_key_takeaways(moments, evaluations),
        })

    return slides


# =============================================================================
# Student-Level Slide Generation (full deck from rich feedback)
# =============================================================================

def generate_student_presentation_slides(
    feedback: Dict[str, Any],
    moments: Optional[List[Dict[str, Any]]] = None,
    evaluations: Optional[List[Dict[str, Any]]] = None,
    transcript: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate the full student-level presentation deck from rich feedback data.

    Combines student feedback sections (scenario, clinical skills, ABCDE, NTS,
    CRM, learning outcomes) with optional moment/evaluation data for a complete
    ~32-slide debrief presentation.

    Args:
        feedback: Student feedback dictionary (from student_feedback_*.json)
        moments: Optional list of critical moments
        evaluations: Optional list of evaluations
        transcript: Optional transcript segments

    Returns:
        List of slide objects for the complete deck
    """
    slides = []
    slide_index = 0
    session_id = feedback.get('session_id', '')

    # ── 1. Title Slide ──
    student_name = feedback.get('student_name')
    student_id = feedback.get('student_id', '')
    display_name = student_name or _format_student_id(student_id)

    slides.append({
        "slide_number": slide_index,
        "type": "title",
        "title": "Clinical Simulation Debrief",
        "subtitle": display_name,
        "content": {
            "role": feedback.get('student_role'),
            "session_id": session_id,
            "scenario_type": feedback.get('scenario_details', {}).get('scenario_type'),
            "status": feedback.get('status'),
        },
    })
    slide_index += 1

    # ── 2. Scenario Context ──
    scenario = feedback.get('scenario_details', {})
    if scenario.get('patient_presentation') or scenario.get('learning_objectives'):
        slides.append({
            "slide_number": slide_index,
            "type": "scenario",
            "title": "Scenario Context",
            "content": {
                "patient_presentation": scenario.get('patient_presentation'),
                "clinical_context": scenario.get('clinical_context'),
                "learning_objectives": scenario.get('learning_objectives', []),
            },
            "presenter_notes": (
                "Review the patient presentation with the student. "
                "Confirm understanding of learning objectives. "
                "Set expectations for the debrief discussion."
            ),
            "duration_suggestion": 60,
        })
        slide_index += 1

    # ── 3. Timeline (if moments provided) ──
    if moments:
        timeline_slide, slide_index = _generate_timeline_slide(moments, slide_index)
        if timeline_slide:
            slides.append(timeline_slide)

    # ── 4. Moment Evidence/Feedback Pairs (if moments provided) ──
    if moments:
        moment_slides, slide_index = _generate_moment_slides(
            moments, evaluations or [], transcript, slide_index
        )
        slides.extend(moment_slides)

    # ── 5. Clinical Skills (one slide per skill with data) ──
    for skill in feedback.get('clinical_skills', []):
        observations = skill.get('observations', [])
        summary = skill.get('summary', '')

        # Only generate if there's meaningful data
        if not observations and not summary:
            continue

        first_obs = observations[0] if observations else None

        slides.append({
            "slide_number": slide_index,
            "type": "clinical_skill",
            "title": skill.get('skill_name'),
            "subtitle": skill.get('protocol_reference'),
            "content": {
                "rating": skill.get('performance_rating'),
                "summary": summary,
                "observations": observations,
            },
            "video_clip": {
                "start": first_obs.get('timestamp_start'),
                "end": first_obs.get('timestamp_end'),
            } if first_obs and first_obs.get('timestamp_start') else None,
            "presenter_notes": (
                f"Performance rating: {skill.get('performance_rating', '?')}/5. "
                f"{summary}\n"
                "Discussion: What were you thinking at this moment? "
                "What would you do differently?"
            ),
            "duration_suggestion": 120,
        })
        slide_index += 1

    # ── 6. ABCDE Assessment ──
    abcde = feedback.get('abcde_assessment')
    if abcde:
        slides.append({
            "slide_number": slide_index,
            "type": "abcde",
            "title": "ABCDE Assessment",
            "content": abcde,
            "presenter_notes": (
                "Walk me through your assessment process. "
                "What findings guided your priorities?"
            ),
            "duration_suggestion": 180,
        })
        slide_index += 1

    # ── 7. NTS Overview ──
    nts = feedback.get('non_technical_skills', {})
    nts_components = ['communication', 'teamwork', 'leadership',
                      'situational_awareness', 'decision_making']

    nts_content = {
        comp: {"rating": nts.get(comp, {}).get('rating')}
        for comp in nts_components
    }
    nts_content['overall_nts_rating'] = nts.get('overall_nts_rating')

    slides.append({
        "slide_number": slide_index,
        "type": "nts_overview",
        "title": "Non-Technical Skills",
        "content": nts_content,
        "presenter_notes": "Overview slide — detailed discussion on individual skill slides that follow.",
        "duration_suggestion": 60,
    })
    slide_index += 1

    # ── 8. Individual NTS Skill Slides (conditional) ──
    nts_labels = {
        'communication': 'Communication',
        'teamwork': 'Teamwork',
        'leadership': 'Leadership',
        'situational_awareness': 'Situational Awareness',
        'decision_making': 'Decision Making',
    }

    for comp_key in nts_components:
        comp = nts.get(comp_key, {})
        strengths = comp.get('strengths', [])
        areas = comp.get('areas_for_improvement', [])
        observations = comp.get('observations', [])

        # Only generate if there's meaningful data
        if not strengths and not areas and not observations:
            continue

        label = nts_labels.get(comp_key, comp_key.replace('_', ' ').title())
        slides.append({
            "slide_number": slide_index,
            "type": "nts_skill",
            "title": label,
            "content": {
                "rating": comp.get('rating'),
                "strengths": strengths,
                "areas_for_improvement": areas,
                "observations": observations,
            },
            "presenter_notes": (
                f"How did you approach {label.lower()} during this scenario? "
                "What challenges did you face?"
            ),
            "duration_suggestion": 90,
        })
        slide_index += 1

    # ── 9. CRM Reflection ──
    crm = feedback.get('crm_reflection', {})
    if crm.get('strengths') or crm.get('areas_for_development'):
        slides.append({
            "slide_number": slide_index,
            "type": "crm",
            "title": "Crisis Resource Management",
            "content": crm,
            "presenter_notes": (
                "Focus on team dynamics and resource utilization. "
                "Discuss the 10-for-10 principle if applicable."
            ),
            "duration_suggestion": 120,
        })
        slide_index += 1

    # ── 10. Learning Outcomes ──
    outcomes = feedback.get('learning_outcomes', {})
    achievements = outcomes.get('key_achievements', [])
    areas_for_improvement = outcomes.get('areas_for_improvement', [])

    if achievements or areas_for_improvement:
        slides.append({
            "slide_number": slide_index,
            "type": "learning_outcomes",
            "title": "Key Learning Points",
            "content": {
                "key_achievements": achievements,
                "areas_for_improvement": areas_for_improvement,
                "debrief_summary": outcomes.get('debrief_summary'),
            },
            "presenter_notes": "Summarize key points. Ask student to identify their top takeaway.",
            "duration_suggestion": 120,
        })
        slide_index += 1

    # ── 11. Action Plan ──
    action_plan = outcomes.get('action_plan', [])
    if action_plan:
        slides.append({
            "slide_number": slide_index,
            "type": "action_plan",
            "title": "Action Plan",
            "content": {
                "action_items": action_plan,
                "recommended_focus": outcomes.get('recommended_focus', []),
            },
            "presenter_notes": "Agree on specific follow-up actions and timeline.",
            "duration_suggestion": 60,
        })
        slide_index += 1

    # ── 12. Discussion & Q&A ──
    slides.append({
        "slide_number": slide_index,
        "type": "discussion",
        "title": "Discussion",
        "subtitle": "Questions & Reflection",
        "content": {
            "prompts": [
                "What was the most challenging aspect of this scenario?",
                "What would you do differently next time?",
                "How will you apply these learnings in practice?",
                "Any questions about the feedback provided?",
            ],
        },
        "presenter_notes": "Open floor for discussion. Allow the student to lead reflection.",
        "duration_suggestion": 300,
    })
    slide_index += 1

    # ── 13. Summary & Close ──
    evidence_chain = feedback.get('evidence_chain', {})
    references = feedback.get('references', [])

    # Count strengths vs growth items for ratio bar
    strength_count = len(achievements)
    for skill in feedback.get('clinical_skills', []):
        if skill.get('performance_rating', 0) >= 4:
            strength_count += 1
    for comp_key in nts_components:
        strength_count += len(nts.get(comp_key, {}).get('strengths', []))
    strength_count += len(crm.get('strengths', []))

    growth_count = len(areas_for_improvement)
    for skill in feedback.get('clinical_skills', []):
        if skill.get('performance_rating', 0) <= 2:
            growth_count += 1
    for comp_key in nts_components:
        growth_count += len(nts.get(comp_key, {}).get('areas_for_improvement', []))
    growth_count += len(crm.get('areas_for_development', []))

    slides.append({
        "slide_number": slide_index,
        "type": "summary",
        "title": "Debrief Summary",
        "content": {
            "debrief_summary": outcomes.get('debrief_summary'),
            "evidence_count": len(evidence_chain.get('evidence_links', [])),
            "references_count": len(references),
            "references": references,
            "key_achievements": achievements,
            "strength_count": strength_count,
            "growth_count": growth_count,
        },
        "presenter_notes": "Closing remarks. Provide a copy of this presentation to the student.",
        "duration_suggestion": 30,
    })

    return slides


# =============================================================================
# Export helper (kept for backward compatibility)
# =============================================================================

def export_slides_to_json(slides: List[Dict[str, Any]]) -> str:
    """Export slides to JSON format."""
    return json.dumps(slides, indent=2)
