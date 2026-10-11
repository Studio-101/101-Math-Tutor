import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_skill_prompt(skill_name: str) -> str:
    """
    Reads .agents/skills/{skill_name}/SKILL.md and removes YAML frontmatter.
    Also appends AGENTS.md global instructions if available.
    """
    skill_path = PROJECT_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill file not found at: {skill_path}")
    
    content = skill_path.read_text(encoding="utf-8")
    
    # Strip YAML frontmatter (between --- and ---)
    content_stripped = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    
    # Check if global AGENTS.md exists
    agents_md = PROJECT_ROOT / "AGENTS.md"
    global_rules = ""
    if agents_md.exists():
        global_rules = agents_md.read_text(encoding="utf-8")
    
    combined = f"""[GLOBAL SYSTEM RULES]
{global_rules}

[CURRENT ROLE & SKILL INSTRUCTIONS: {skill_name}]
{content_stripped.strip()}
"""
    return combined.strip()

def load_all_skills() -> dict[str, str]:
    """Preloads all three core skills."""
    return {
        "tutor_coordinator": load_skill_prompt("tutor_coordinator"),
        "math_solver": load_skill_prompt("math_solver"),
        "shape_tutor": load_skill_prompt("shape_tutor"),
    }
