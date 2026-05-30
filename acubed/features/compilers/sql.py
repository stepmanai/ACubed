# features/compilers/sql.py


class SQLCompiler:
    def column(self, expr):
        return expr.name

    def literal(self, expr):
        return str(expr.value)

    def add(self, expr):
        return f"({expr.left.compile(self)} + {expr.right.compile(self)})"

    def divide(self, expr):
        return f"({expr.left.compile(self)} / {expr.right.compile(self)})"

    def multiply(self, expr):
        return f"({expr.left.compile(self)} * {expr.right.compile(self)})"

    def count(self, expr):
        return f"COUNT({expr.expr.compile(self)})"

    def avg(self, expr):
        return f"AVG({expr.expr.compile(self)})"

    def stddev(self, expr):
        return f"STDDEV({expr.expr.compile(self)})"

    def rolling_mean(self, expr):
        inner = expr.expr.compile(self)

        return f"""
        AVG({inner})
        OVER (
            ROWS BETWEEN {expr.window_size} PRECEDING
            AND CURRENT ROW
        )
        """
