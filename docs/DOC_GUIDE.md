# Documentation Guide for Human–AI Software Development  

**Purpose**: Establish lightweight, repeatable documentation practices for projects built by AI coding agents with human collaboration.  

---

## Core Principles  

1. **Docs are Code** – Generate and maintain documentation as part of every coding cycle.  
2. **Accuracy > Completeness** – Outdated docs are worse than missing ones.  
3. **Layered Documentation** – Provide quick references for common use and detailed notes for architecture and history.  
4. **Human + AI Roles** – AI generates and updates docs, human validates and adds context.  
5. **Centralized Documentation** – All project documentation must be consolidated in the root `/docs` directory.

---

## Documentation Centralization Requirements

### Single Source of Truth Principle

**All project documentation MUST be located in `/docs` at the project root.**

- **No component-specific docs folders** (e.g., `backend/docs`, `gui/docs`, `frontend/docs`)
- **No scattered documentation** across multiple directories
- **Single consolidated location** for all project knowledge

### Directory Structure Standard

```
project-root/
├── docs/              # ALL documentation goes here
│   ├── DOC_GUIDE.md  # This guide (centralization requirements)
│   ├── ARCHITECTURE.md
│   ├── CHANGELOG.md
│   ├── USER_GUIDE.md
│   ├── DEVNOTES.md
│   ├── COLLAB.md
│   ├── SECURITY.md
│   └── ERROR_CODES.md
├── src/              # Source code only
├── backend/          # Backend code only (no docs/ folder)
├── frontend/         # Frontend code only (no docs/ folder)
└── gui/              # GUI code only (no docs/ folder)
```

### Migration Guidelines

When consolidating existing fragmented documentation:

1. **Identify all docs folders** across the project
2. **Analyze duplicate files** for unique content
3. **Merge identical files** into single authoritative versions
4. **Combine related content** from different components
5. **Move all documentation** to root `/docs` directory
6. **Update all internal links** to point to centralized locations
7. **Remove empty docs folders** after migration
8. **Test all documentation links** for accessibility

### Enforcement Rules

- **AI Agents**: Never create component-specific documentation folders
- **AI Agents**: Always place new documentation in `/docs`
- **AI Agents**: When updating docs, check for and consolidate any scattered versions
- **Humans**: Review centralization during documentation validation cycles
- **Build Systems**: Can include checks to prevent docs folder proliferation

---

## Documentation Types  

### 1. Inline Documentation  
- **Docstrings** for every function/class (purpose, params, returns, errors).  
- **Update** whenever functionality changes.  

### 2. Architecture Notes (`ARCHITECTURE.md`)  
- Explain system design, module responsibilities, and reasoning.  
- Update when adding/removing modules or changing data flow.  

### 3. Change Log (`CHANGELOG.md`)  
- Every change entry includes:  
  - **Date**  
  - **Feature or fix**  
  - **Reason or root cause**  
  - **Resolution/approach**  
- Serves as memory for future AI agents.  

### 4. Usage Guide (`USER_GUIDE.md`)  
- Simple runnable examples (common + advanced use).  
- Update when defaults, flags, or behaviors change.  

### 5. Security & Ethics Notes (`SECURITY.md`)  
- Summarize project safety constraints (read-only, rate limits, etc.).  
- Include explicit authorized-use disclaimer.  

---

## AI Responsibilities  

- Always generate/update **docstrings** for code changes.  
- Add/update entries in `CHANGELOG.md` when modifying features.  
- Update `ARCHITECTURE.md` when altering structure or design.  
- Provide or update examples in `USER_GUIDE.md` when adding features.  
- Document security/ethical boundaries when relevant.  
- **Ensure all documentation is placed in `/docs`** - never create component-specific docs folders.
- **Consolidate scattered documentation** when encountered during any task.

---

## Human Responsibilities  

- Review AI-generated docs for clarity and accuracy.  
- Add domain context, rationale, and real-world testing notes.  
- Ensure documentation reflects actual behavior in production.  
- **Validate centralization** - verify no documentation exists outside `/docs`.

---

## Best Practices  

- **Small Updates**: Update docs in the same commit as code changes.  
- **Traceability**: Each bug fix includes documented cause and resolution.  
- **Consistency**: Follow identical patterns across all modules and projects.  
- **Review Cycle**: Humans validate docs during testing and before release.  
- **Centralization**: Always consolidate documentation in root `/docs` directory.

---

## Quick Checklist for AI Agents  

- [ ] Docstrings updated for all new/modified functions.  
- [ ] `CHANGELOG.md` entry added with date + rationale.  
- [ ] `ARCHITECTURE.md` updated if structure changed.  
- [ ] `USER_GUIDE.md` updated with examples for new/changed features.  
- [ ] `SECURITY.md` reviewed if new functionality affects safety/ethics.  
- [ ] **All documentation placed in `/docs` directory.**
- [ ] **No component-specific docs folders created.**
- [ ] **Existing scattered documentation consolidated when encountered.**

---

**Key Insight**: Documentation is not optional overhead. It is a core part of collaboration, enabling humans and future AI agents to maintain, extend, and trust the codebase. All documentation must be centralized in `/docs` for maximum effectiveness and maintainability.