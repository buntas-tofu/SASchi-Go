"""Read-only operation-tree traversal shared by compilation and validation.

Walking a node does not execute it or admit its operation kind. The default
follows the supported control containers. Guard scans may inspect structural
containers of unknown kinds as well, preserving conservative source checks.
"""
from collections.abc import Mapping


def walk_operations(ops, *, all_containers=False):
    """Yield original object/mapping nodes in source-order preorder.

    Compiled roots may contain serialized children. Preserve their identity and
    payloads, including statically present zero-trip bodies. Runtime execution
    retains its separate IF and DO scheduling and operation allowlists.
    """
    for op in ops:
        yield op
        kind, args = (op['kind'], op['args']) if isinstance(op, Mapping) else (op.kind, op.args)
        if kind == 'if' or (all_containers and 'operation' in args):
            yield from walk_operations([args['operation']], all_containers=all_containers)
        if kind == 'do_counted' or (all_containers and 'body' in args):
            body = args.get('body')
            if not isinstance(body, list):
                label = 'counted DO' if kind == 'do_counted' else 'operation'
                raise ValueError(f'{label} body must be a list')
            yield from walk_operations(body, all_containers=all_containers)
