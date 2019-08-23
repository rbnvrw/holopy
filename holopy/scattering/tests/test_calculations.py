# Copyright 2011-2016, Vinothan N. Manoharan, Thomas G. Dimiduk,
# Rebecca W. Perry, Jerome Fung, Ryan McGorty, Anna Wang, Solomon Barkley
#
# This file is part of HoloPy.
#
# HoloPy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HoloPy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HoloPy.  If not, see <http://www.gnu.org/licenses/>.
"""
Base class for scattering theories.  Implements python-based
calc_intensity and calc_holo, based on subclass's calc_field

.. moduleauthor:: Thomas G. Dimiduk <tdimiduk@physics.harvard.edu>
.. moduleauthor:: R. Alexander <ralexander@g.harvard.edu>
"""
import unittest

from nose.plugins.attrib import attr

from holopy.scattering import (Sphere, Spheres, LayeredSphere, Mie, Multisphere,
                               Spheroid, Cylinder, Tmatrix)
from holopy.core import detector_grid
from holopy.core.tests.common import assert_obj_close
from holopy.scattering.calculations import *
from holopy.scattering.errors import MissingParameter

import xarray as xr

SCATTERER = Sphere(n=1.6, r=.5, center=(5, 5, 5))
MED_INDEX = 1.33
LOCATIONS = detector_grid(shape=(20, 20), spacing=.1)
WAVELEN = 0.66
POL = (0, 1)


class TestCalculations(unittest.TestCase):
    @attr('fast')
    def test_calc_holo(self):
        holo = calc_holo(LOCATIONS, SCATTERER, MED_INDEX, WAVELEN, POL)
        self.assertTrue(True)

    @attr('medium')
    def test_calc_field(self):
        field = calc_field(LOCATIONS, SCATTERER, MED_INDEX, WAVELEN, POL)
        self.assertTrue(True)

    @attr('fast')
    def test_calc_cross_sections(self):
        cross = calc_cross_sections(SCATTERER, MED_INDEX, WAVELEN, POL)
        self.assertTrue(True)

    @attr('medium')
    def test_calc_intensity(self):
        intensity = calc_intensity(LOCATIONS, SCATTERER, MED_INDEX, WAVELEN, POL)
        self.assertTrue(True)

    @attr('fast')
    def test_calc_scat_matrix(self):
        matr = calc_scat_matrix(LOCATIONS, SCATTERER, MED_INDEX, WAVELEN)
        self.assertTrue(True)

    @attr('fast')
    def test_finalize(self):
        result = finalize(LOCATIONS.values, LOCATIONS)
        expected = copy_metadata(LOCATIONS.values, LOCATIONS)
        self.assertTrue(result.equals(expected))

    @attr('medium')
    def test_scattered_field_to_hologram(self):
        size = 3
        coords = np.linspace(0, 1, size)
        scat = xr.DataArray(np.array([1, 0, 0]), coords=[('vector', coords)])
        ref = xr.DataArray(np.array([1, 0, 0]), coords=[('vector', coords)])
        normals = np.array((0, 0, 1))
        correct_holo = (np.abs(scat + ref)**2).sum(dim='vector')
        holo = scattered_field_to_hologram(scat, ref, normals)
        self.assertEqual(holo.values.mean(), correct_holo.values.mean())


class TestDetermineDefaultTheoryFor(unittest.TestCase):
    @attr('fast')
    def test_determine_default_theory_for_sphere(self):
        default_theory = determine_default_theory_for(Sphere())
        correct_theory = Mie()
        self.assertTrue(default_theory == correct_theory)

    @attr('fast')
    def test_determine_default_theory_for_spheres(self):
        default_theory = determine_default_theory_for(
            Spheres([Sphere(), Sphere()]))
        correct_theory = Multisphere()
        self.assertTrue(default_theory == correct_theory)

    @attr('fast')
    def test_determine_default_theory_for_spheroid(self):
        scatterer = Spheroid(n=1.33, r=(1.0, 2.0))
        default_theory = determine_default_theory_for(scatterer)
        correct_theory = Tmatrix()
        self.assertTrue(default_theory == correct_theory)

    @attr('fast')
    def test_determine_default_theory_for_cylinder(self):
        scatterer = Cylinder(n=1.33, h=2, d=1)
        default_theory = determine_default_theory_for(scatterer)
        correct_theory = Tmatrix()
        self.assertTrue(default_theory == correct_theory)

    @attr('fast')
    def test_determine_default_theory_for_layered_sphere(self):

        default_theory = determine_default_theory_for(LayeredSphere())
        correct_theory = Mie()
        self.assertTrue(default_theory == correct_theory)


class TestPrepSchema(unittest.TestCase):
    @attr('fast')
    def test_wavelength_missing(self):
        args = (LOCATIONS, MED_INDEX, None, POL)
        self.assertRaises(MissingParameter, prep_schema, *args)

    @attr('fast')
    def test_medium_index_missing(self):
        args = (LOCATIONS, None, WAVELEN, POL)
        self.assertRaises(MissingParameter, prep_schema, *args)

    @attr('fast')
    def test_polarization_missing(self):
        args = (LOCATIONS, MED_INDEX, WAVELEN, None)
        self.assertRaises(MissingParameter, prep_schema, *args)

    @attr('fast')
    def test_multiple_illumination_via_polarization_shape(self):
        coords = ['red', 'green']
        polarization = xr.DataArray(np.array([[1, 0], [0, 1]]),
                                    coords=[('illumination', coords),
                                            ('vector', ['x', 'y'])])
        prep_schema(LOCATIONS, MED_INDEX, WAVELEN, polarization)
        self.assertTrue(True)

    @attr('fast')
    def test_multiple_illumination_via_detector_wavelength_shape(self):
        coords = ['red', 'green']
        wavelength = xr.DataArray(np.array([0.66, 0.532]),
                                  coords=[('illumination', coords)])
        prep_schema(LOCATIONS, MED_INDEX, wavelength, POL)
        self.assertTrue(True)


class TestInterpretTheory(unittest.TestCase):
    @attr('fast')
    def test_interpret_auto_theory(self):
        theory = interpret_theory(SCATTERER, theory='auto')
        theory_ok = type(theory) == Mie
        self.assertTrue(theory_ok)

    @attr('fast')
    def test_interpret_specified_theory(self):
        theory = interpret_theory(SCATTERER, theory=Mie)
        theory_ok = type(theory) == Mie
        self.assertTrue(theory_ok)

if __name__ == '__main__':
    unittest.main()
