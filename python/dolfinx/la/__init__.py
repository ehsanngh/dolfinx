# Copyright (C) 2017-2025 Garth N. Wells, Jack S. Hale
#
# This file is part of DOLFINx (https://www.fenicsproject.org)
#
# SPDX-License-Identifier:    LGPL-3.0-or-later
"""Linear algebra functionality"""

import typing

import numpy as np
import numpy.typing as npt

import dolfinx
from dolfinx import cpp as _cpp
from dolfinx.cpp.common import IndexMap
from dolfinx.cpp.la import BlockMode, InsertMode, Norm

__all__ = [
    "InsertMode",
    "MatrixCSR",
    "Norm",
    "Vector",
    "is_orthonormal",
    "matrix_csr",
    "norm",
    "orthonormalize",
    "vector",
]


class Vector:
    _cpp_object: typing.Union[
        _cpp.la.Vector_float32,
        _cpp.la.Vector_float64,
        _cpp.la.Vector_complex64,
        _cpp.la.Vector_complex128,
        _cpp.la.Vector_int8,
        _cpp.la.Vector_int32,
        _cpp.la.Vector_int64,
    ]

    def __init__(
        self,
        x: typing.Union[
            _cpp.la.Vector_float32,
            _cpp.la.Vector_float64,
            _cpp.la.Vector_complex64,
            _cpp.la.Vector_complex128,
            _cpp.la.Vector_int8,
            _cpp.la.Vector_int32,
            _cpp.la.Vector_int64,
        ],
    ):
        """A distributed vector object.

        Args:
            x: C++ Vector object.

        Note:
            This initialiser is intended for internal library use only.
            User code should call :func:`vector` to create a vector object.
        """
        self._cpp_object = x
        self._petsc_x = None

    def __del__(self):
        if self._petsc_x is not None:
            self._petsc_x.destroy()

    @property
    def index_map(self) -> IndexMap:
        """Index map that describes size and parallel distribution."""
        return self._cpp_object.index_map

    @property
    def block_size(self) -> int:
        """Block size for the vector."""
        return self._cpp_object.bs

    @property
    def array(self) -> np.ndarray:
        """Local representation of the vector."""
        return self._cpp_object.array

    @property
    def petsc_vec(self):
        """PETSc vector holding the entries of the vector.

        Upon first call, this function creates a PETSc ``Vec`` object
        that wraps the degree-of-freedom data. The ``Vec`` object is
        cached and the cached ``Vec`` is returned upon subsequent calls.

        Note:
          When the object is destroyed it will destroy the underlying
          petsc4py vector automatically.
        """
        assert dolfinx.has_petsc4py

        from dolfinx.la.petsc import create_vector_wrap

        if self._petsc_x is None:
            self._petsc_x = create_vector_wrap(self)
        return self._petsc_x

    def scatter_forward(self) -> None:
        """Update ghost entries."""
        self._cpp_object.scatter_forward()

    def scatter_reverse(self, mode: InsertMode) -> None:
        """Scatter ghost entries to owner.

        Args:
            mode: Control how scattered values are set/accumulated by
                owner.
        """
        self._cpp_object.scatter_reverse(mode)


class MatrixCSR:
    _cpp_object: typing.Union[
        _cpp.la.MatrixCSR_float32,
        _cpp.la.MatrixCSR_float64,
        _cpp.la.MatrixCSR_complex64,
        _cpp.la.MatrixCSR_complex128,
    ]

    def __init__(
        self,
        A: typing.Union[
            _cpp.la.MatrixCSR_float32,
            _cpp.la.MatrixCSR_float64,
            _cpp.la.MatrixCSR_complex64,
            _cpp.la.MatrixCSR_complex128,
        ],
    ):
        """A distributed sparse matrix that uses compressed sparse row
        storage.

        Note:
            Objects of this type should be created using
            :func:`matrix_csr` and not created using this initialiser.

        Args:
            A: The C++/nanobind matrix object.
        """
        self._cpp_object = A

    def index_map(self, i: int) -> IndexMap:
        """Index map for row/column.

        Args:
            i: 0 for row map, 1 for column map.
        """
        return self._cpp_object.index_map(i)

    def mult(self, x: Vector, y: Vector) -> None:
        """Compute ``y += Ax``.

        Args:
            x: Input Vector
            y: Output Vector
        """
        self._cpp_object.mult(x._cpp_object, y._cpp_object)

    @property
    def block_size(self) -> list:
        """Block sizes for the matrix."""
        return self._cpp_object.bs

    def add(
        self,
        x: npt.NDArray[np.floating],
        rows: npt.NDArray[np.int32],
        cols: npt.NDArray[np.int32],
        bs: int = 1,
    ) -> None:
        """Add a block of values in the matrix."""
        self._cpp_object.add(x, rows, cols, bs)

    def set(
        self,
        x: npt.NDArray[np.floating],
        rows: npt.NDArray[np.int32],
        cols: npt.NDArray[np.int32],
        bs: int = 1,
    ) -> None:
        """Set a block of values in the matrix."""
        self._cpp_object.set(x, rows, cols, bs)

    def set_value(self, x: np.floating) -> None:
        """Set all non-zero entries to a value.

        Args:
            x: The value to set all non-zero entries to.
        """
        self._cpp_object.set_value(x)

    def scatter_reverse(self) -> None:
        """Scatter and accumulate ghost values."""
        self._cpp_object.scatter_reverse()

    def squared_norm(self) -> np.floating:
        """Compute the squared Frobenius norm.

        Note:
            This operation is collective and requires communication.
        """
        return self._cpp_object.squared_norm()

    @property
    def data(self) -> npt.NDArray[np.floating]:
        """Underlying matrix entry data."""
        return self._cpp_object.data

    @property
    def indices(self) -> npt.NDArray[np.int32]:
        """Local column indices."""
        return self._cpp_object.indices

    @property
    def indptr(self) -> npt.NDArray[np.int64]:
        """Local row pointers."""
        return self._cpp_object.indptr

    def to_dense(self) -> npt.NDArray[np.floating]:
        """Copy to a dense 2D array.

        Note:
            Typically used for debugging.
        """
        return self._cpp_object.to_dense()

    def to_scipy(self, ghosted: bool = False):
        """Convert to a SciPy CSR/BSR matrix. Data is shared.

        Note:
            SciPy must be available.

        Args:
            ghosted: If ``True`` rows that are ghosted in parallel are
                included in the returned SciPy matrix, otherwise ghost
                rows are not included.

        Returns:
            SciPy compressed sparse row (both block sizes equal to one)
            or a SciPy block compressed sparse row matrix.
        """
        bs0, bs1 = self._cpp_object.bs
        ncols = self.index_map(1).size_local + self.index_map(1).num_ghosts
        if ghosted:
            nrows = self.index_map(0).size_local + self.index_map(0).num_ghosts
            data, indices, indptr = self.data, self.indices, self.indptr
        else:
            nrows = self.index_map(0).size_local
            nnzlocal = self.indptr[nrows]
            data, indices, indptr = (
                self.data[: (bs0 * bs1) * nnzlocal],
                self.indices[:nnzlocal],
                self.indptr[: nrows + 1],
            )

        if bs0 == 1 and bs1 == 1:
            from scipy.sparse import csr_matrix as _csr

            return _csr((data, indices, indptr), shape=(nrows, ncols))
        else:
            from scipy.sparse import bsr_matrix as _bsr

            return _bsr(
                (data.reshape(-1, bs0, bs1), indices, indptr), shape=(bs0 * nrows, bs1 * ncols)
            )


def matrix_csr(
    sp: _cpp.la.SparsityPattern, block_mode=BlockMode.compact, dtype: npt.DTypeLike = np.float64
) -> MatrixCSR:
    """Create a distributed sparse matrix.

    The matrix uses compressed sparse row storage.

    Args:
        sp: The sparsity pattern that defines the nonzero structure of
            the matrix the parallel distribution of the matrix.
        dtype: The scalar type.

    Returns:
        A sparse matrix.
    """
    if np.issubdtype(dtype, np.float32):
        ftype = _cpp.la.MatrixCSR_float32
    elif np.issubdtype(dtype, np.float64):
        ftype = _cpp.la.MatrixCSR_float64
    elif np.issubdtype(dtype, np.complex64):
        ftype = _cpp.la.MatrixCSR_complex64
    elif np.issubdtype(dtype, np.complex128):
        ftype = _cpp.la.MatrixCSR_complex128
    else:
        raise NotImplementedError(f"Type {dtype} not supported.")

    return MatrixCSR(ftype(sp, block_mode))


def vector(map, bs=1, dtype: npt.DTypeLike = np.float64) -> Vector:
    """Create a distributed vector.

    Args:
        map: Index map the describes the size and distribution of the
            vector.
        bs: Block size.
        dtype: The scalar type.

    Returns:
        A distributed vector.
    """
    if np.issubdtype(dtype, np.float32):
        vtype = _cpp.la.Vector_float32
    elif np.issubdtype(dtype, np.float64):
        vtype = _cpp.la.Vector_float64
    elif np.issubdtype(dtype, np.complex64):
        vtype = _cpp.la.Vector_complex64
    elif np.issubdtype(dtype, np.complex128):
        vtype = _cpp.la.Vector_complex128
    elif np.issubdtype(dtype, np.int8):
        vtype = _cpp.la.Vector_int8
    elif np.issubdtype(dtype, np.int32):
        vtype = _cpp.la.Vector_int32
    elif np.issubdtype(dtype, np.int64):
        vtype = _cpp.la.Vector_int64
    else:
        raise NotImplementedError(f"Type {dtype} not supported.")

    return Vector(vtype(map, bs))


def orthonormalize(basis: list[Vector]):
    """Orthogonalise set of vectors in-place."""
    _cpp.la.orthonormalize([x._cpp_object for x in basis])


def is_orthonormal(basis: list[Vector], eps: float = 1.0e-12) -> bool:
    """Check that list of vectors are orthonormal."""
    return _cpp.la.is_orthonormal([x._cpp_object for x in basis], eps)


def norm(x: Vector, type: _cpp.la.Norm = _cpp.la.Norm.l2) -> np.floating:
    """Compute a norm of the vector.

    Args:
        x: Vector to measure.
        type: Norm type to compute.

    Returns:
        Computed norm.
    """
    return _cpp.la.norm(x._cpp_object, type)
