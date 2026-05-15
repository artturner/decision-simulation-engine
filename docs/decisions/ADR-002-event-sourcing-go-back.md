# ADR-002: Event Sourcing for Go Back

**Decision**: Use immutable events per play and deterministic replay for rewind.  
**Rationale**:
- Supports auditability
- Enables rewind without state mutation
- Enables analytics on paths  
**Status**: Accepted
