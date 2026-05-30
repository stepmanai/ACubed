# features/expressions/arithmetic.py

from .base import Expression


class BinaryOp(Expression):
    def __init__(self, left: Expression, right: Expression):
        self.left = left
        self.right = right


class Add(BinaryOp):
    def compile(self, compiler):
        return compiler.add(self)


class Divide(BinaryOp):
    def compile(self, compiler):
        return compiler.divide(self)


class Multiply(BinaryOp):
    def compile(self, compiler):
        return compiler.multiply(self)
