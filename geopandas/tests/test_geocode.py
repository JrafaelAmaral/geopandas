from __future__ import absolute_import

from fiona.crs import from_epsg
import pandas as pd
import pandas.util.testing as tm
from shapely.geometry import Point
import geopandas as gpd
import pytest

from geopandas import GeoSeries
from geopandas.tools import geocode, reverse_geocode
from geopandas.tools.geocoding import _prepare_geocode_result

from geopandas.tests.util import unittest, mock, assert_geoseries_equal


def _skip_if_no_geopy():
    try:
        import geopy
    except ImportError:
        raise pytest.skip("Geopy not installed. Skipping tests.")
    except SyntaxError:
        raise pytest.skip("Geopy is known to be broken on Python 3.2. "
                          "Skipping tests.")


class ForwardMock(mock.MagicMock):
    """
    Mock the forward geocoding function.
    Returns the passed in address and (p, p+.5) where p increases
    at each call

    """
    def __init__(self, *args, **kwargs):
        super(ForwardMock, self).__init__(*args, **kwargs)
        self._n = 0.0

    def __call__(self, *args, **kwargs):
        self.return_value = args[0], (self._n, self._n + 0.5)
        self._n += 1
        return super(ForwardMock, self).__call__(*args, **kwargs)


class ReverseMock(mock.MagicMock):
    """
    Mock the reverse geocoding function.
    Returns the passed in point and 'address{p}' where p increases
    at each call

    """
    def __init__(self, *args, **kwargs):
        super(ReverseMock, self).__init__(*args, **kwargs)
        self._n = 0

    def __call__(self, *args, **kwargs):
        self.return_value = 'address{0}'.format(self._n), args[0]
        self._n += 1
        return super(ReverseMock, self).__call__(*args, **kwargs)


class TestGeocode(unittest.TestCase):
    def setUp(self):
        _skip_if_no_geopy()
        self.locations = ['260 Broadway, New York, NY',
                          '77 Massachusetts Ave, Cambridge, MA']
        self.points = [Point(-71.0597732, 42.3584308),
                       Point(-77.0365305, 38.8977332)]

    def test_prepare_result(self):
        # Calls _prepare_result with sample results from the geocoder call
        # loop
        p0 = Point(12.3, -45.6) # Treat these as lat/lon
        p1 = Point(-23.4, 56.7)
        d = {'a': ('address0', p0.coords[0]),
             'b': ('address1', p1.coords[0])}

        df = _prepare_geocode_result(d)
        assert type(df) is gpd.GeoDataFrame
        self.assertEqual(from_epsg(4326), df.crs)
        self.assertEqual(len(df), 2)
        self.assert_('address' in df)

        coords = df.loc['a']['geometry'].coords[0]
        test = p0.coords[0]
        # Output from the df should be lon/lat
        self.assertAlmostEqual(coords[0], test[1])
        self.assertAlmostEqual(coords[1], test[0])

        coords = df.loc['b']['geometry'].coords[0]
        test = p1.coords[0]
        self.assertAlmostEqual(coords[0], test[1])
        self.assertAlmostEqual(coords[1], test[0])

    def test_prepare_result_none(self):
        p0 = Point(12.3, -45.6) # Treat these as lat/lon
        d = {'a': ('address0', p0.coords[0]),
             'b': (None, None)}

        df = _prepare_geocode_result(d)
        assert type(df) is gpd.GeoDataFrame
        self.assertEqual(from_epsg(4326), df.crs)
        self.assertEqual(len(df), 2)
        self.assert_('address' in df)

        row = df.loc['b']
        self.assertEqual(len(row['geometry'].coords), 0)
        self.assert_(pd.np.isnan(row['address']))
    
    def test_bad_provider_forward(self):
        with self.assertRaises(ValueError):
            geocode(['cambridge, ma'], 'badprovider')

    def test_bad_provider_reverse(self):
        with self.assertRaises(ValueError):
            reverse_geocode(['cambridge, ma'], 'badprovider')

    def test_forward(self):
        with mock.patch('geopy.geocoders.googlev3.GoogleV3.geocode',
                        ForwardMock()) as m:
            g = geocode(self.locations, provider='googlev3', timeout=2)
            self.assertEqual(len(self.locations), m.call_count)

        n = len(self.locations)
        self.assertIsInstance(g, gpd.GeoDataFrame)
        expected = GeoSeries([Point(float(x) + 0.5, float(x)) for x in range(n)],
                             crs=from_epsg(4326))
        assert_geoseries_equal(expected, g['geometry'])
        tm.assert_series_equal(g['address'],
                               pd.Series(self.locations, name='address'))

    def test_reverse(self):
        with mock.patch('geopy.geocoders.googlev3.GoogleV3.reverse',
                        ReverseMock()) as m:
            g = reverse_geocode(self.points, provider='googlev3', timeout=2)
            self.assertEqual(len(self.points), m.call_count)

        self.assertIsInstance(g, gpd.GeoDataFrame)

        expected = GeoSeries(self.points, crs=from_epsg(4326))
        assert_geoseries_equal(expected, g['geometry'])
        address = pd.Series(['address' + str(x) for x in range(len(self.points))],
                            name='address')
        tm.assert_series_equal(g['address'], address)
