# Shared ability and effect names — parser version 9

The collector now keeps an item effect and a class ability with the same name as separate records. Item effects have an explicit `record_kind`, and the merge identity includes that kind. Repeated class-ability evidence still retains source variants as before. This avoids combining unlike mechanics merely because their display names match.

The evidence index preserves `record_kind` and adds `by_kind` for filtering item effects separately from ordinary ability records. The existing name index remains available for finding all candidate research with the same display name.

All 102 tests pass. A synthetic two-page collection verifies that a same-named class ability and item effect both survive publication with separate source records and no merged variants. Existing delivered raw batches remain unchanged.
