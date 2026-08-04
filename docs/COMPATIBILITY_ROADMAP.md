# Structurizr Java Compatibility Roadmap

> **Historical — this roadmap is complete.** All four phases landed as
> PP-31 → PP-35; the "78% compatible / 22–30 hours remaining" figures below
> describe the state *before* that work and are kept as a record of what was
> planned and why. The resulting breaking changes are documented in
> [MIGRATION.md](./MIGRATION.md).
>
> For where the project stands **now**, read
> [structurizr-parity.md](./structurizr-parity.md) (feature parity against the
> Java Structurizr UI) and [roadmap.md](./roadmap.md) (the forward plan).

**Status at the time of writing:** 78% Compatible (189/249 fields implemented)  
**Target:** 100% Compatible  
**Total Effort:** 22-30 hours across 4 phases

---

## Executive Summary

pystructurizr needs to implement missing Structurizr Java data model fields to achieve full compatibility. The analysis identified 36 missing/mismatched fields across static structure, views, deployment, and configuration models.

This roadmap breaks the work into 4 phases, each increasing compatibility:
- **Phase 1:** Critical fixes → 90% compatibility (4-6 hours)
- **Phase 2:** Important fields → 95% compatibility (8-12 hours)
- **Phase 3:** Structural refactoring → 98% compatibility (6-8 hours)
- **Phase 4:** Complete features → 100% compatibility (4-6 hours)

---

## Phase 1: Critical Fixes (4-6 hours) → **90% Compatibility**

### Why This Phase First
Fixes blocking issues that break JSON round-trip compatibility and core functionality.

### Tasks

#### 1.1 Fix DeploymentNode.instances Type
**Priority:** CRITICAL  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
# Before
@dataclass
class DeploymentNode:
    instances: str = "1"  # ❌ String

# After
@dataclass
class DeploymentNode:
    instances: int = 1    # ✅ Integer
```

**Impact:** 
- Fixes JSON serialization/deserialization
- Aligns with Structurizr Java model
- Allows numeric calculations on instance counts

**Testing:**
- Update `tests/test_parser/test_json_parser.py` to verify `instances` is parsed as int
- Add round-trip test: JSON → parse → serialize → compare

**Time:** 5 minutes  
**Risk:** Low (simple type change)

---

#### 1.2 Add Relationship.linkedRelationshipId Field (Already Present ✅)
**Status:** Already implemented in current code

---

#### 1.3 Add Missing Parent References
**Priority:** CRITICAL  
**Files:** `src/pystructurizr/models.py`

**Changes needed:**

```python
# Add to Container
@dataclass
class Container:
    id: str
    name: str
    # ... existing fields ...
    parent_id: str = ""  # NEW: Reference to parent SoftwareSystem

# Add to Component
@dataclass
class Component:
    id: str
    name: str
    # ... existing fields ...
    parent_id: str = ""  # NEW: Reference to parent Container

# Add to DeploymentNode
@dataclass
class DeploymentNode:
    id: str
    name: str
    # ... existing fields ...
    parent_id: str = ""  # NEW: Reference to parent DeploymentNode

# Add to InfrastructureNode
@dataclass
class InfrastructureNode:
    id: str
    name: str
    # ... existing fields ...
    parent_id: str = ""  # NEW: Reference to parent DeploymentNode
```

**Impact:**
- Enables hierarchy reconstruction from flat model
- Required for proper element traversal
- Needed for parent-child relationships in views

**Parser Updates:**
- Update JSON parser to set parent_id when parsing nested elements
- Update DSL parser similarly

**Testing:**
- Add tests for hierarchy traversal
- Verify parent_id is correctly set when parsing nested structures
- Test Workspace.find_element() with hierarchy

**Time:** 45 minutes  
**Risk:** Low (read-only fields, backward compatible)

---

#### 1.4 Fix AutomaticLayout Default Values
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
# Before
@dataclass
class AutomaticLayout:
    rank_direction: RankDirection = RankDirection.TOP_BOTTOM
    rank_separation: int = 300      # ❌ Wrong
    node_separation: int = 300      # ❌ Wrong
    edge_separation: int = 0
    vertices: bool = False

# After
@dataclass
class AutomaticLayout:
    rank_direction: RankDirection = RankDirection.TOP_BOTTOM
    rank_separation: int = 100      # ✅ Correct
    node_separation: int = 100      # ✅ Correct
    edge_separation: int = 0
    vertices: bool = False
```

**Impact:**
- Fixes default diagram layout spacing
- Aligns with Structurizr Java defaults
- Affects all auto-generated view layouts

**Testing:**
- Update test fixtures to use correct defaults
- Verify Mermaid generation with new spacing

**Time:** 5 minutes  
**Risk:** Low (default value change)

---

#### 1.5 Add Perspective.title Field
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
# Before
@dataclass
class Perspective:
    name: str
    description: str = ""
    value: str = ""
    url: str = ""

# After
@dataclass
class Perspective:
    name: str
    description: str = ""
    value: str = ""
    url: str = ""
    title: str = ""  # NEW: Display title for perspective
```

**Parser Updates:**
- JSON parser: `json_data.get("title", "")`
- DSL parser: handle `title` property

**Testing:**
- Add round-trip test for perspective with title
- Verify title persistence in JSON serialization

**Time:** 15 minutes  
**Risk:** Low (additive, backward compatible)

---

### Phase 1 Verification Checklist
- [ ] All type changes compile without warnings
- [ ] Existing tests still pass
- [ ] New tests for parent_id hierarchy pass
- [ ] JSON round-trip tests pass
- [ ] Mermaid generation still works with new defaults
- [ ] No mypy --strict violations

**Estimated Total Time:** 4-6 hours  
**Expected Compatibility:** 90%

---

## Phase 2: Important Fields (8-12 hours) → **95% Compatibility**

### Why This Phase
Adds significant missing functionality for workspace metadata and enhanced view customization.

### Tasks

#### 2.1 Add Workspace Metadata Fields
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
@dataclass
class Workspace:
    name: str
    description: str = ""
    # ... existing fields ...
    
    # NEW fields
    id: str = ""                          # Workspace ID (read from JSON)
    version: int = 1                      # Version number
    revision: int = 1                     # Revision number
    last_modified_date: str = ""          # ISO 8601 timestamp
    last_modified_by: str = ""            # User who last modified
    created_date: str = ""                # ISO 8601 timestamp
    created_by: str = ""                  # User who created
```

**Parser Updates:**
- JSON parser: Extract from workspace root level
- Update field mapping in `_parse_json_dict()`

**Testing:**
- Round-trip test with all metadata fields
- Verify metadata preservation

**Time:** 1 hour  
**Risk:** Low (read-only metadata)

---

#### 2.2 Add View Element and Relationship Customization Fields
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Changes:**

```python
# Add to ViewElement
@dataclass
class ViewElement:
    id: str
    x: Optional[int] = None
    y: Optional[int] = None
    
    # NEW fields
    title: str = ""         # Custom element title in this view
    description: str = ""   # Custom element description in this view
    width: Optional[int] = None   # Custom width in this view
    height: Optional[int] = None  # Custom height in this view

# Add to RelationshipView
@dataclass
class RelationshipView:
    id: str
    description: str = ""
    url: str = ""
    order: str = ""
    response: Optional[bool] = None
    
    # NEW fields
    title: str = ""                    # Custom relationship label
    link: Optional[bool] = None        # Is this a link?
    link_element: Optional[int] = None # Position as element link
```

**Parser Updates:**
- JSON parser: map `title`, `description` for ViewElement
- Parse RelationshipView enhanced fields

**Testing:**
- Test custom view element titles
- Test relationship label customization
- Round-trip tests

**Time:** 2 hours  
**Risk:** Medium (affects View structure)

---

#### 2.3 Add View Control Fields
**Priority:** MEDIUM  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
@dataclass
class View:
    type: ViewType
    key: str
    # ... existing fields ...
    
    # NEW fields
    owner: str = ""                  # View owner/responsible person
    disable_automatic_layout: bool = False  # Disable auto-layout
    hide_element_metadata: bool = False     # Hide element metadata in view
    hide_relationship_metadata: bool = False  # Hide relationship metadata
```

> **The last two were a mistake and were removed in PP-90.** No such
> fields exist in Structurizr — not in `structurizr-core`, not in the DSL,
> not in the workspace JSON schema. Metadata visibility is a *style*
> property (`ElementStyle.metadata`/`.description` and the relationship
> equivalents), which is what the renderers honour. Do not re-add them.

**Impact:**
- Enables view-level customization
- Allows disabling automatic layout for specific views
- Metadata visibility control

**Parser Updates:**
- JSON parser: extract boolean flags

**Testing:**
- Verify flags are preserved in JSON round-trip

**Time:** 1 hour  
**Risk:** Low

---

#### 2.4 Add Terminology Default Values
**Priority:** MEDIUM  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
# Before
@dataclass
class Terminology:
    enterprise: str = ""
    person: str = ""
    software_system: str = ""
    container: str = ""
    component: str = ""
    code: str = ""
    deployment_node: str = ""
    infrastructure_node: str = ""
    relationship: str = ""

# After (with proper defaults)
@dataclass
class Terminology:
    enterprise: str = "Enterprise"
    person: str = "Person"
    software_system: str = "Software System"
    container: str = "Container"
    component: str = "Component"
    code: str = "Code"
    deployment_node: str = "Deployment Node"
    infrastructure_node: str = "Infrastructure Node"
    relationship: str = "Relationship"
```

**Impact:**
- Aligns with Structurizr defaults
- Affects default view labels

**Testing:**
- Verify default terminology in views
- Test override behavior

**Time:** 30 minutes  
**Risk:** Low

---

#### 2.5 Add Deployment Node Icon Support
**Priority:** MEDIUM  
**File:** `src/pystructurizr/models.py`  
**Changes:**

```python
@dataclass
class DeploymentNode:
    # ... existing fields ...
    icon: str = ""  # NEW: Icon URL or name

@dataclass
class InfrastructureNode:
    # ... existing fields ...
    icon: str = ""  # NEW: Icon URL or name
```

**Parser Updates:**
- JSON parser: extract `icon` field
- DSL parser: handle icon in deployment definitions

**Testing:**
- Round-trip tests with icons

**Time:** 45 minutes  
**Risk:** Low

---

### Phase 2 Verification Checklist
- [ ] All new fields have proper type hints
- [ ] JSON parser handles all new fields
- [ ] DSL parser supports new fields
- [ ] Round-trip tests pass for all new fields
- [ ] Existing functionality not broken
- [ ] Test coverage remains > 90%

**Estimated Total Time:** 8-12 hours  
**Expected Compatibility:** 95%

---

## Phase 3: Structural Refactoring (6-8 hours) → **98% Compatibility**

### Why This Phase
Aligns pystructurizr's structure with official Structurizr Java implementation by separating Model and ViewSet concerns.

### Current vs Target Structure

**Current (Flattened):**
```
Workspace
├── people[]
├── software_systems[]
├── relationships[]
├── deployment_nodes[]
├── views[]
├── configuration
```

**Target (Structured like Java):**
```
Workspace
├── model: Model
│   ├── people[]
│   ├── software_systems[]
│   ├── relationships[]
│   ├── deployment_nodes[]
│   └── enterprise
├── views: ViewSet
│   ├── system_landscape_views[]
│   ├── system_context_views[]
│   ├── container_views[]
│   ├── component_views[]
│   ├── dynamic_views[]
│   ├── deployment_views[]
│   └── configuration
```

### Tasks

#### 3.1 Create Model Dataclass
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
@dataclass
class Model:
    """Represents the static model (elements and relationships)."""
    people: list[Person] = field(default_factory=list)
    software_systems: list[SoftwareSystem] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    deployment_nodes: list[DeploymentNode] = field(default_factory=list)
    enterprise: Optional[Enterprise] = None
    deployment_environments: list[str] = field(default_factory=list)
    
    def find_element(self, element_id: str) -> ...:
        """Look up any element by id across all levels."""
        # Move existing Workspace.find_element logic here
        pass
    
    def all_relationships_for(self, ids: set[str]) -> list[Relationship]:
        """Return relationships where both source and destination are in ids."""
        # Move existing Workspace.all_relationships_for logic here
        pass
```

**Migration Strategy:**
- Create Model class as new entity
- Move element lookup logic to Model
- Workspace delegates to model

**Testing:**
- All existing tests should still pass
- Verify element lookup works through new structure

**Time:** 2 hours  
**Risk:** Medium (refactoring existing logic)

---

#### 3.2 Create ViewSet Dataclass
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
@dataclass
class ViewSet:
    """Represents all views and their configuration."""
    system_landscape_views: list[View] = field(default_factory=list)
    system_context_views: list[View] = field(default_factory=list)
    container_views: list[View] = field(default_factory=list)
    component_views: list[View] = field(default_factory=list)
    dynamic_views: list[View] = field(default_factory=list)
    deployment_views: list[View] = field(default_factory=list)
    custom_views: list[View] = field(default_factory=list)
    filtered_views: list[View] = field(default_factory=list)
    configuration: Configuration = field(default_factory=Configuration)
    
    def get_all_views(self) -> list[View]:
        """Return all views regardless of type."""
        all_views = []
        all_views.extend(self.system_landscape_views)
        all_views.extend(self.system_context_views)
        all_views.extend(self.container_views)
        all_views.extend(self.component_views)
        all_views.extend(self.dynamic_views)
        all_views.extend(self.deployment_views)
        all_views.extend(self.custom_views)
        all_views.extend(self.filtered_views)
        return all_views
```

**Benefits:**
- Type-safe view organization
- Easier to work with specific view types
- Matches Java implementation

**Testing:**
- Verify all views are accessible
- Test view retrieval by type

**Time:** 2 hours  
**Risk:** Medium

---

#### 3.3 Refactor Workspace to Use Model and ViewSet
**Priority:** HIGH  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
@dataclass
class Workspace:
    name: str
    description: str = ""
    model: Model = field(default_factory=Model)      # NEW
    views: ViewSet = field(default_factory=ViewSet)  # NEW
    
    # Deprecated (kept for backward compatibility)
    @property
    def people(self) -> list[Person]:
        """Backward compatibility."""
        return self.model.people
    
    @property
    def software_systems(self) -> list[SoftwareSystem]:
        """Backward compatibility."""
        return self.model.software_systems
    
    # ... other delegating properties ...
```

**Migration Strategy:**
- Add new attributes
- Keep old attributes as properties delegating to model/views
- Gradual migration path for users

**Backward Compatibility:**
- Old code `ws.people.append(...)` still works
- New code can use `ws.model.people.append(...)`
- Deprecation warnings in docstrings

**Testing:**
- All existing tests use deprecated properties
- Add new tests using model/views structure
- Verify both paths work identically

**Time:** 2 hours  
**Risk:** High (breaking change in structure, mitigated by backward compatibility)

---

#### 3.4 Update JSON Parser for New Structure
**Priority:** HIGH  
**File:** `src/pystructurizr/parser/json_parser.py`  
**Change:**
```python
def _parse_json_dict(data: dict[str, Any]) -> Workspace:
    ws_data = data.get("workspace", data)
    model_data = ws_data.get("model", {})
    views_data = ws_data.get("views", {})
    
    # Parse model
    model = Model(
        people=[_parse_person(p) for p in model_data.get("people", [])],
        software_systems=[...],
        relationships=[...],
        deployment_nodes=[...],
        enterprise=_parse_enterprise(model_data.get("enterprise")) if "enterprise" in model_data else None,
        deployment_environments=list(model_data.get("deploymentEnvironments", []))
    )
    
    # Parse views
    views = ViewSet(
        system_landscape_views=[_parse_view(v, ViewType.SYSTEM_LANDSCAPE) for v in views_data.get("systemLandscapeViews", [])],
        system_context_views=[...],
        # ... etc
        configuration=_parse_configuration(views_data.get("configuration"))
    )
    
    return Workspace(
        name=ws_data.get("name", ""),
        description=ws_data.get("description", ""),
        model=model,
        views=views
    )
```

**Testing:**
- All existing JSON parsing tests should still pass
- Add new tests for Model and ViewSet parsing

**Time:** 2 hours  
**Risk:** Medium (parser refactoring)

---

#### 3.5 Update DSL Parser for New Structure
**Priority:** MEDIUM  
**File:** `src/pystructurizr/parser/dsl.py`

**Changes:** Similar to JSON parser, create Model and ViewSet during parsing

**Testing:**
- All DSL tests still pass
- Verify correct structure created

**Time:** 2 hours  
**Risk:** Medium

---

### Phase 3 Verification Checklist
- [ ] New Model class created with all element logic
- [ ] New ViewSet class created with view organization
- [ ] Workspace refactored to use model/views
- [ ] All deprecated properties work for backward compatibility
- [ ] JSON parser updated for new structure
- [ ] DSL parser updated for new structure
- [ ] All existing tests pass
- [ ] New tests for model/views structure pass
- [ ] JSON round-trip produces correct structure
- [ ] No mypy --strict violations

**Estimated Total Time:** 6-8 hours  
**Expected Compatibility:** 98%

---

## Phase 4: Complete Features (4-6 hours) → **100% Compatibility**

### Tasks

#### 4.1 Add CustomElement Icon and Metadata
**Priority:** LOW  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
# Update existing field (already present)
@dataclass
class CustomElement:
    # metadata field already exists
    metadata: str = ""  # Already present ✅
    icon: str = ""      # NEW: Icon URL or name
```

**Time:** 15 minutes  
**Risk:** Low

---

#### 4.2 Add Configuration Branding and Export Support
**Priority:** LOW  
**File:** `src/pystructurizr/models.py`  
**Change:**
```python
@dataclass
class Branding:
    """Custom branding configuration."""
    color: str = ""      # Brand color
    font: str = ""       # Brand font
    logo: str = ""       # Logo URL

@dataclass
class Configuration:
    styles: Styles = field(default_factory=Styles)
    themes: list[str] = []
    terminology: Terminology = field(default_factory=Terminology)
    default_view: str = ""
    view_sort_order: Optional[ViewSortOrder] = None
    properties: dict[str, str] = {}
    
    # NEW fields
    branding: Optional[Branding] = None  # Custom branding
    generators_and_exporters: dict[str, str] = field(default_factory=dict)  # Export config
```

**Parser Updates:**
- Parse branding configuration from JSON
- Parse generators/exporters

**Testing:**
- Round-trip tests for branding

**Time:** 1.5 hours  
**Risk:** Low

---

#### 4.3 Add Advanced Metadata Support
**Priority:** LOW  
**File:** `src/pystructurizr/models.py`  
**Changes:**

```python
@dataclass
class Documentation:
    """Additional documentation."""
    content: str = ""       # Documentation content
    format: str = "Markdown"  # Format type

# Add to Workspace
@dataclass
class Workspace:
    # ... existing fields ...
    documentation: list[Documentation] = field(default_factory=list)  # NEW
    decisions: list[str] = field(default_factory=list)  # NEW: ADR links
```

**Time:** 1 hour  
**Risk:** Low

---

#### 4.4 Add Validation and Constraint Support
**Priority:** MEDIUM  
**Implementation:**

```python
from typing import Annotated
from pydantic import Field

# Update key constraints
@dataclass
class View:
    type: ViewType
    key: str  # Must be unique within workspace
    # Validate key is not empty and follows naming conventions
```

**Consider:** Adding pydantic-core for validation if not already present

**Time:** 1.5 hours  
**Risk:** Medium

---

#### 4.5 Documentation and Migration Guide
**Priority:** HIGH  
**Files:** Create new documentation  
**Content:**
- Migration guide from old to new structure
- Field mapping reference
- Compatibility matrix
- Examples

**Time:** 1 hour  
**Risk:** Low

---

### Phase 4 Verification Checklist
- [ ] All remaining fields implemented
- [ ] Round-trip JSON tests pass for all fields
- [ ] Documentation complete
- [ ] Migration guide published
- [ ] Test coverage maintained > 90%
- [ ] mypy --strict compliance verified
- [ ] All fields match Java implementation

**Estimated Total Time:** 4-6 hours  
**Expected Compatibility:** 100%

---

## Implementation Timeline Suggestion

### Week 1: Phase 1 (Critical Fixes)
- **Mon-Tue:** Tasks 1.1, 1.3 (types and parents)
- **Wed:** Task 1.4, 1.5 (defaults and title)
- **Thu-Fri:** Testing and verification

### Week 2: Phase 2 (Important Fields)
- **Mon-Tue:** Tasks 2.1, 2.2 (workspace and view customization)
- **Wed-Thu:** Tasks 2.3, 2.4, 2.5 (controls and icons)
- **Fri:** Testing and verification

### Week 3-4: Phase 3 (Structural Refactoring)
- **Week 3:** Tasks 3.1, 3.2, 3.3 (Model, ViewSet, Workspace)
- **Week 4:** Tasks 3.4, 3.5 (Parser updates)
- **End of Week 4:** Full testing and backward compatibility

### Week 5: Phase 4 (Complete Features)
- **Mon-Wed:** Tasks 4.1-4.4 (remaining fields and validation)
- **Thu-Fri:** Documentation and final verification

**Total Timeline:** 5 weeks  
**Total Effort:** 22-30 hours

---

## Risk Mitigation

### High Risk Areas
1. **Structural Refactoring (Phase 3)**
   - Mitigation: Extensive backward compatibility layer
   - Mitigation: Feature flag approach if needed
   - Mitigation: Detailed migration guide

2. **Parser Changes (Phase 3)**
   - Mitigation: Comprehensive round-trip tests
   - Mitigation: Regression test suite
   - Mitigation: Dual-parsing during transition

### Medium Risk Areas
1. **Type Changes (Phase 1)**
   - Mitigation: Simple, isolated changes
   - Mitigation: Type checking with mypy

2. **Field Additions (Phase 2)**
   - Mitigation: Backward compatible (all have defaults)
   - Mitigation: Optional fields used throughout

---

## Verification Strategy

### Testing at Each Phase
- Unit tests for new fields
- Integration tests for parsers
- Round-trip JSON tests (parse → serialize → compare)
- Mermaid generation regression tests
- Backward compatibility tests

### Quality Gates
- ✅ 90%+ test coverage maintained
- ✅ mypy --strict compliance
- ✅ No regressions in existing functionality
- ✅ JSON round-trip consistency
- ✅ Backward compatibility preserved (except Phase 3 with deprecation)

---

## Jira Tickets to Create

### Main Epic/Task
**Title:** Achieve 100% Structurizr Java Compatibility (PP-31)

**Subtasks:**
1. **PP-32:** Phase 1 - Critical Fixes (4-6h) → 90% compatibility
2. **PP-33:** Phase 2 - Important Fields (8-12h) → 95% compatibility  
3. **PP-34:** Phase 3 - Structural Refactoring (6-8h) → 98% compatibility
4. **PP-35:** Phase 4 - Complete Features (4-6h) → 100% compatibility

---

## Success Criteria

- ✅ All 249 fields implemented in pystructurizr
- ✅ 100% type compatibility with Structurizr Java
- ✅ Perfect JSON round-trip fidelity
- ✅ Test coverage > 90%
- ✅ Zero mypy --strict violations
- ✅ Backward compatibility maintained
- ✅ Comprehensive documentation

---

## Next Steps

1. **Review this roadmap** with team
2. **Create Jira tickets** for each phase
3. **Estimate sprint capacity** and schedule
4. **Begin Phase 1** (critical fixes)
5. **Establish review process** for compatibility changes
