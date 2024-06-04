from unittest import TestCase

from common.sentinel import Sentinel


class TestSentinel(TestCase):
    def test_identity(self):
        self.assertTrue(Sentinel is Sentinel)
        self.assertTrue(Sentinel is Sentinel())

    def test_equality(self):
        self.assertTrue(Sentinel == Sentinel)
        self.assertTrue(Sentinel == Sentinel())

    def test_different_than_none(self):
        self.assertTrue(Sentinel is not None)

    def test_instantion_fails(self):
        with self.assertRaisesRegex(TypeError, "does not accept arguments"):
            Sentinel(None)

        with self.assertRaisesRegex(TypeError, "does not accept arguments"):
            Sentinel(p1="kwarg")

    def test_repr(self):
        self.assertEqual("Sentinel", repr(Sentinel))

    def test_bool_evaluation(self):
        value = "value"
        if Sentinel:
            value = Sentinel

        not_value = "not_value"
        if not Sentinel:
            not_value = Sentinel

        self.assertEqual(Sentinel, value)
        self.assertEqual("not_value", not_value)
