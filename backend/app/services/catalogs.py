from sqlalchemy import func, select
from app.models.professional import Company, Skill, GuidanceArea

CATALOGS = {"companies": Company, "skills": Skill, "guidance-areas": GuidanceArea}
SEEDS = {
    Company: ["Microsoft", "Amazon", "Google", "Infosys", "TCS", "Accenture"],
    Skill: [
        "Java", "Python", "SQL", "FastAPI", "Spring Boot", "Docker", "JavaScript", "Data Analysis",
        "C", "C++", "C#", "TypeScript", "HTML", "CSS", "Git", "Linux", "PostgreSQL", "MySQL",
        "REST APIs", "Django", "Flask", "Node.js", "React", "Angular", "Vue.js", ".NET",
        "Data Structures", "Algorithms", "Object-Oriented Programming", "System Design",
        "Software Testing", "Test Automation", "CI/CD", "AWS", "Microsoft Azure", "Google Cloud",
        "Pandas", "NumPy", "Machine Learning", "Deep Learning", "Power BI", "Tableau", "Excel",
        "Cybersecurity", "Computer Networks", "Embedded Systems", "Internet of Things",
        "MATLAB", "VLSI Design", "AutoCAD", "SolidWorks", "UI/UX Design", "Figma",
        "Technical Writing", "Communication", "Problem Solving", "Project Management",
    ],
    GuidanceArea: [
        "Placement Guidance", "Interview Preparation", "Higher Studies", "Software Development",
        "Data Science", "Internships", "Career Guidance", "Resume Review", "Portfolio Review",
        "Coding Interview Preparation", "System Design Interviews", "Core Engineering Careers",
        "Research Opportunities", "Study Abroad", "Scholarship Applications", "Career Transitions",
        "Product Management", "Entrepreneurship", "Open Source Contributions", "Professional Networking",
    ],
}


def seed_catalogs(db):
    # Names, rather than fixed IDs, make this safe to run repeatedly.
    for model, names in SEEDS.items():
        for name in names:
            if not db.scalar(select(model.id).where(func.lower(model.name) == name.lower())):
                db.add(model(name=name))
    db.commit()
