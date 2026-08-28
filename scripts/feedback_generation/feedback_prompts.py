"""
Feedback Generation Prompts
Templates for generating structured clinical feedback using LLMs
"""

SYSTEM_PROMPT = """You are an expert clinical educator specializing in nursing education and simulation-based learning.

Your role is to provide constructive, evidence-based feedback to nursing students based on their performance during clinical simulations. Your feedback should be:

1. **Specific**: Reference exact moments with timestamps
2. **Evidence-based**: Cite observed actions and behaviors
3. **Balanced**: Acknowledge strengths and areas for improvement
4. **Educational**: Explain the clinical reasoning and standards
5. **Actionable**: Provide concrete recommendations for improvement

You evaluate performance across these clinical competency categories:
- Patient Assessment
- Medication Management
- Infection Control
- Communication Skills
- Emergency Recognition and Response
- Physical Examination
- Patient Safety
- Clinical Reasoning"""

FEEDBACK_GENERATION_PROMPT = """Generate comprehensive clinical feedback for a nursing student based on their performance during a simulated patient encounter.

## Scenario Context
{scenario_context}

## Student Performance Data

### Student Information
- **Person ID**: {person_id}
- **Role**: {role}
- **Total Actions Performed**: {total_actions}
- **Critical Actions**: {critical_actions}

### Timeline of Actions
{action_timeline}

### Activity Summary by Category
{category_summary}

### Critical Moments
{critical_moments}

---

## Instructions

Generate structured feedback in the following format:

### 1. Overall Performance Summary
Provide a 2-3 sentence overview of the student's performance.

### 2. Competency-Based Feedback

For each relevant clinical competency:

#### [Competency Name]
**Strengths:**
- [Specific observed strength with timestamp]
- [Another strength if applicable]

**Areas for Improvement:**
- [Specific area needing work with timestamp]
- [Recommendation for improvement]

**Clinical Rationale:**
[Brief explanation of why this matters clinically]

### 3. Critical Incident Analysis
If there were any critical incidents (emergency recognition, urgent response):
- What happened (with timestamp)
- What the student did well
- What could be improved
- Learning points

### 4. Key Recommendations
Top 3-5 actionable recommendations for future practice.

### 5. Reflective Questions
2-3 questions to encourage student reflection on their performance.

---

Generate the feedback now in a professional, supportive, and educational tone."""

SCENARIO_CONTEXT_TEMPLATE = """
**Patient**: George Harrison, 74-year-old male
**Presenting Condition**: Chest infection, admitted for IV antibiotics
**Critical Event**: Anaphylactic reaction to antibiotic (moxifloxacin)
**Learning Objectives**:
- Perform comprehensive patient assessment
- Administer medications safely with appropriate monitoring
- Recognize and respond to anaphylactic reactions
- Demonstrate effective emergency management
- Communicate clearly with patients and team members
"""

def format_action_timeline(actions: list, limit: int = 20) -> str:
    """Format action timeline for prompt"""
    timeline_str = ""

    # Show first N actions and last few critical ones
    display_actions = actions[:limit]

    for action in display_actions:
        timestamp_min = int(action['timestamp'] // 60)
        timestamp_sec = int(action['timestamp'] % 60)

        timeline_str += f"- **[{timestamp_min}:{timestamp_sec:02d}]** "
        timeline_str += f"{action['category']}: {action['action_type']}\n"
        timeline_str += f"  Text: \"{action['text'][:100]}...\"\n"
        timeline_str += f"  Confidence: {action['confidence']:.2f}\n\n"

    if len(actions) > limit:
        timeline_str += f"\n... and {len(actions) - limit} more actions\n"

    return timeline_str

def format_category_summary(categories: dict) -> str:
    """Format category summary"""
    summary_str = ""
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        summary_str += f"- **{category}**: {count} actions\n"
    return summary_str

def format_critical_moments(actions: list) -> str:
    """Format critical moments (critical/high importance)"""
    critical = [a for a in actions if a['importance'] in ['critical', 'high']]

    if not critical:
        return "No critical moments identified.\n"

    moments_str = f"Found {len(critical)} critical moments:\n\n"

    for action in critical[:10]:  # Show top 10 critical
        timestamp_min = int(action['timestamp'] // 60)
        timestamp_sec = int(action['timestamp'] % 60)

        moments_str += f"- **[{timestamp_min}:{timestamp_sec:02d}]** {action['category']}\n"
        moments_str += f"  Action: {action['action_type']}\n"
        moments_str += f"  Importance: {action['importance']}\n"
        moments_str += f"  Text: \"{action['text'][:150]}...\"\n\n"

    return moments_str

def build_feedback_prompt(person_timeline: dict, scenario_context: str = None) -> str:
    """
    Build complete feedback generation prompt

    Args:
        person_timeline: Person timeline data from Stage 3
        scenario_context: Optional scenario context (uses default if not provided)

    Returns:
        Complete prompt string
    """
    if scenario_context is None:
        scenario_context = SCENARIO_CONTEXT_TEMPLATE

    # Extract data from timeline
    person_id = person_timeline['person_id']
    role = person_timeline['role']
    total_actions = person_timeline['total_actions']
    critical_actions = person_timeline['critical_actions']
    actions = person_timeline['actions']
    categories = person_timeline['categories']

    # Format components
    action_timeline = format_action_timeline(actions)
    category_summary = format_category_summary(categories)
    critical_moments = format_critical_moments(actions)

    # Build complete prompt
    prompt = FEEDBACK_GENERATION_PROMPT.format(
        scenario_context=scenario_context,
        person_id=person_id,
        role=role,
        total_actions=total_actions,
        critical_actions=critical_actions,
        action_timeline=action_timeline,
        category_summary=category_summary,
        critical_moments=critical_moments
    )

    return prompt
