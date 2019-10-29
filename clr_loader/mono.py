import atexit

from .ffi import load_mono, ffi


__all__ = ["Mono"]


_MONO = None
_ROOT_DOMAIN = None


class Mono:
    def __init__(self, domain=None):
        self._assemblies = {}
        initialize()

        if domain is None:
            self._domain = _ROOT_DOMAIN
        else:
            raise NotImplementedError

    def get_callable(self, assembly_path, typename, function):
        assembly = self._assemblies.get(assembly_path)
        if not assembly:
            assembly = _MONO.mono_domain_assembly_open(
                self._domain, assembly_path.encode("utf8")
            )
            _check_result(assembly, f"Unable to load assembly {assembly_path}")
            self._assemblies[assembly_path] = assembly

        image = _MONO.mono_assembly_get_image(assembly)
        _check_result(image, "Unable to load image from assembly")

        desc = MethodDesc(typename, function)
        method = desc.search(image)
        _check_result(
            method, f"Could not find method {typename}.{function} in assembly"
        )

        return MonoMethod(self._domain, method)


class MethodDesc:
    def __init__(self, typename, function):
        self._desc = f"{typename}:{function}"
        self._ptr = _MONO.mono_method_desc_new(
            self._desc.encode("utf8"),
            1 # include_namespace
        )

    def search(self, image):
        return _MONO.mono_method_desc_search_in_image(self._ptr, image)

    def __del__(self):
        if _MONO:
            _MONO.mono_method_desc_free(self._ptr)

class MonoMethod:
    def __init__(self, domain, ptr):
        self._ptr = ptr
    
    def __call__(self, ptr, size):
        exception = ffi.new("MonoObject**")
        params = ffi.new("void*[2]")

        params[0] = ffi.new("void**", ptr)
        params[1] = ffi.new("int*", size)

        res = _MONO.mono_runtime_invoke(self._ptr, ffi.NULL, params, exception)
        _check_result(res, "Failed to call method")

        unboxed = ffi.cast("int32_t*", _MONO.mono_object_unbox(res))
        _check_result(unboxed, "Failed to convert result to int")

        return unboxed[0]


def initialize(path=None, gc=None):
    global _MONO, _ROOT_DOMAIN
    if _MONO is None:
        _MONO = load_mono(path=path, gc=gc)
        _ROOT_DOMAIN = _MONO.mono_jit_init(b"clr_loader")
        _check_result(_ROOT_DOMAIN, "Failed to initialize Mono")
        atexit.register(_release)


def _release():
    if _ROOT_DOMAIN is not None and _MONO is not None:
        _MONO.mono_jit_cleanup(_ROOT_DOMAIN)
        _MONO = None
        _ROOT_DOMAIN = None


def _check_result(res, msg):
    if res == ffi.NULL or not res:
        raise RuntimeError(msg)
