# features/compilers/runtime.py

import statistics


class RuntimeCompiler:
    def column(self, expr):
        return lambda row: row[expr.name]

    def literal(self, expr):
        return lambda row: expr.value

    def add(self, expr):
        left = expr.left.compile(self)
        right = expr.right.compile(self)

        return lambda row: left(row) + right(row)

    def divide(self, expr):
        left = expr.left.compile(self)
        right = expr.right.compile(self)

        return lambda row: left(row) / right(row)

    def multiply(self, expr):
        left = expr.left.compile(self)
        right = expr.right.compile(self)

        return lambda row: left(row) * right(row)

    def avg(self, expr):
        fn = expr.expr.compile(self)

        return lambda rows: sum(fn(r) for r in rows) / len(rows)

    def stddev(self, expr):
        fn = expr.expr.compile(self)

        return lambda rows: statistics.stdev(fn(r) for r in rows)
