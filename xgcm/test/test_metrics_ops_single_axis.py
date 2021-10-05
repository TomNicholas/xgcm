import numpy as np
import pytest
import xarray as xr

from xgcm.grid import Grid
from xgcm.test.datasets import datasets_grid_metric


@pytest.mark.parametrize("funcname", ["interp", "diff", "min", "max", "cumsum"])
@pytest.mark.parametrize("grid_type", ["B", "C"])
@pytest.mark.parametrize("variable", ["tracer", "u", "v"])
@pytest.mark.parametrize("metric_weighted", ["X", ("Y",), ("X", "Y"), ["X", "Y"]])
@pytest.mark.parametrize("boundary", ["fill", "extend"])
class TestParametrized:
    @pytest.mark.parametrize("axis", ["X", "Y"])
    @pytest.mark.parametrize(
        "periodic", ["True", "False", {"X": True, "Y": False}, {"X": False, "Y": True}]
    )
    def test_weighted_metric(
        self, funcname, grid_type, variable, axis, metric_weighted, periodic, boundary
    ):
        """tests the correct execution of weighted ops along a single axis"""
        # metric_weighted allows the interpolation of e.g. a surface flux to be conservative
        # It multiplies the values with a metric like the area, then performs interpolation
        # and divides by the same metric (area) for the new grid position
        ds, coords, metrics = datasets_grid_metric(grid_type)
        grid = Grid(ds, coords=coords, metrics=metrics, periodic=periodic)
        func = getattr(grid, funcname)

        metric = grid.get_metric(ds[variable], metric_weighted)
        expected_raw = func(ds[variable] * metric, axis, boundary=boundary)
        metric_new = grid.get_metric(expected_raw, metric_weighted)
        expected = expected_raw / metric_new
        new = func(
            ds[variable], axis, metric_weighted=metric_weighted, boundary=boundary
        )
        assert new.equals(expected)

    @pytest.mark.parametrize("multi_axis", ["X", ["X"], ("Y"), ["X", "Y"], ("Y", "X")])
    def test_weighted_metric_multi_axis(
        self, funcname, grid_type, variable, multi_axis, metric_weighted, boundary
    ):
        """tests if the output for multiple axis is the same as when
        executing the single axis ops in serial"""
        ds, coords, metrics = datasets_grid_metric(grid_type)
        grid = Grid(ds, coords=coords, metrics=metrics)

        func = getattr(grid, funcname)
        expected = ds[variable]
        for ax in multi_axis:
            if isinstance(metric_weighted, dict):
                metric_weighted_axis = metric_weighted[ax]
            else:
                metric_weighted_axis = metric_weighted
            expected = func(
                expected,
                ax,
                metric_weighted=metric_weighted_axis,
                boundary=boundary,
            )

        new = func(
            ds[variable],
            multi_axis,
            metric_weighted=metric_weighted,
            boundary=boundary,
        )
        assert new.equals(expected)


@pytest.mark.parametrize(
    "funcname",
    ["interp", "diff", "min", "max", "cumsum", "derivative", "cumint"],
)
@pytest.mark.parametrize("boundary", ["fill", "extend"])
@pytest.mark.parametrize("fill_value", [0, 10, None])
def test_boundary_global_input(funcname, boundary, fill_value):
    """Test that globally defined boundary values result in
    the same output as when the parameters are defined on either
    the grid or axis methods
    """
    ds, coords, metrics = datasets_grid_metric("C")
    axis = "X"

    # Test results by globally specifying fill value/boundary on grid object
    grid_global = Grid(
        ds,
        coords=coords,
        metrics=metrics,
        periodic=False,
        boundary=boundary,
        fill_value=fill_value,
    )
    func_global = getattr(grid_global, funcname)
    global_result = func_global(ds.tracer, axis)

    # Test results by manually specifying fill value/boundary on grid method
    grid_manual = Grid(
        ds, coords=coords, metrics=metrics, periodic=False, boundary=boundary
    )
    func_manual = getattr(grid_manual, funcname)
    manual_result = func_manual(
        ds.tracer, axis, boundary=boundary, fill_value=fill_value
    )
    xr.testing.assert_allclose(global_result, manual_result)


def test_average_unmatched_missing():
    # Tests the behavior of grid.average on an array which has missing values, not present in the metric
    x = np.arange(10)
    data = xr.DataArray(np.ones(10), dims="x", coords={"x": x})
    weights = data * 30
    ds = xr.Dataset({"data": data})
    ds = ds.assign_coords(weights=weights)
    # create an xgcm grid
    grid = Grid(ds, coords={"X": {"center": "x"}}, metrics={"X": ["weights"]})

    # average the unmasked array
    expected = grid.average(ds.data, "X")

    # now lets introduce a missing value in the data
    ds.data[6:8] = np.nan

    # assert that the result for both the full and the masked array is equal,
    # since both only have ones in them.
    xr.testing.assert_allclose(expected, grid.average(ds.data, "X"))


def test_derivative_uniform_grid():
    # this is a uniform grid
    # a non-uniform grid would provide a more rigorous test
    dx = 10.0
    dy = 10.0
    arr = [
        [1.0, 2.0, 4.0, 3.0],
        [4.0, 7.0, 1.0, 2.0],
        [3.0, 1.0, 0.0, 9.0],
        [8.0, 5.0, 2.0, 1.0],
    ]
    ds = xr.Dataset(
        {"foo": (("XC", "YC"), arr)},
        coords={
            "XC": (("XC",), [0.5, 1.5, 2.5, 3.5]),
            "XG": (("XG",), [0, 1.0, 2.0, 3.0]),
            "dXC": (("XC",), [dx, dx, dx, dx]),
            "dXG": (("XG",), [dx, dx, dx, dx]),
            "YC": (("YC",), [0.5, 1.5, 2.5, 3.5]),
            "YG": (("YG",), [0, 1.0, 2.0, 3.0]),
            "dYC": (("YC",), [dy, dy, dy, dy]),
            "dYG": (("YG",), [dy, dy, dy, dy]),
        },
    )

    grid = Grid(
        ds,
        coords={
            "X": {"center": "XC", "left": "XG"},
            "Y": {"center": "YC", "left": "YG"},
        },
        metrics={("X",): ["dXC", "dXG"], ("Y",): ["dYC", "dYG"]},
        periodic=True,
    )

    # Test x direction
    dfoo_dx = grid.derivative(ds.foo, "X")
    expected = grid.diff(ds.foo, "X") / dx
    assert dfoo_dx.equals(expected)

    # Test y direction
    dfoo_dy = grid.derivative(ds.foo, "Y")
    expected = grid.diff(ds.foo, "Y") / dy
    assert dfoo_dy.equals(expected)


def test_derivative_c_grid():
    # test derivatives with synthetic C grid data

    ds, coords, metrics = datasets_grid_metric("C")
    grid = Grid(ds, coords=coords, metrics=metrics)

    # tracer point
    var = "tracer"
    test_axes = ["X", "Y", "Z"]
    test_dx = ["dx_e", "dy_n", "dz_w"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])

    # zonal velocity point
    var = "u"
    test_dx = ["dx_t", "dy_ne", "dz_w_e"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])

    # meridional velocity point
    var = "v"
    test_dx = ["dx_ne", "dy_t", "dz_w_n"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])

    # vertical velocity point
    var = "wt"
    test_dx = ["dx_e", "dy_n", "dz_t"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])


def test_derivative_b_grid():
    # test derivatives with synthetic B grid data

    ds, coords, metrics = datasets_grid_metric("B")
    grid = Grid(ds, coords=coords, metrics=metrics)

    # tracer point
    var = "tracer"
    test_axes = ["X", "Y", "Z"]
    test_dx = ["dx_e", "dy_n", "dz_w"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])

    # zonal velocity point
    var = "u"
    test_dx = ["dx_n", "dy_e", "dz_w_ne"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])

    # meridional velocity point
    var = "v"
    test_dx = ["dx_n", "dy_e", "dz_w_ne"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])

    # vertical velocity point
    var = "wt"
    test_dx = ["dx_e", "dy_n", "dz_t"]
    for ax, dx in zip(test_axes, test_dx):
        _run_single_derivative_test(grid, ax, ds[var], ds[dx])


# run this for each axis and each field in dataset
def _run_single_derivative_test(grid, axis, fld, dx):

    dvar_dx = grid.derivative(fld, axis)
    expected = grid.diff(fld, axis) / dx

    assert dvar_dx.equals(expected.reset_coords(drop=True))
