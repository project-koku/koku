class SentinelMeta(type):
    def __repr__(self):
        return self.__name__


class Sentinel(metaclass=SentinelMeta):
    """An object for testing if a default value was supplied.

    In Python, None is the common sentinel value. In cases where None is a
    valid value, another object is needed.

    This object behaves similarly to None in that it cannot be instantiated and
    can be use for identity and equality comparisons:

    Identity comparison is preferred even though both will work.

        Example:
            Sentinel is Sentinel --> True
            Sentinel == Sentinel --> True


    It can be called with no arguments, though. This works, but is mainly
    intended to prevent usage errors. This should not be done in practice.

        Example:
            Sentinel is Sentinel() --> True


    This object evalutes to True. Generally tests of this object are not useful.

        Example:
            # Not the best use of this object
            if Sentinel:
                print('success')

            --> success


    This can be use as a default value for parameters where None is a valid input.

        Example:
            def sentinel_check(param=Sentinel):
                if param is Sentinel:
                    print("param was not provided")
                    return

                print(f"Something other than '{Sentinel}' was provided: '{param=}'")

            sentinel_check() --> param was not provided
            sentinel_check(param=None) --> Something other than 'Sentinel' was provided: 'param=None'

    """

    def __new__(cls, *args, **kwargs):
        if args or kwargs:
            raise TypeError(f"'{cls!r}' does not accept arguments")

        # Return the class itself and not an instance
        return cls
