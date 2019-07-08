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
.. moduleauthor:: Jerome Fung <jerome.fung@post.harvard.edu>
.. moduleauthor:: Vinothan N. Manoharan <vnm@seas.harvard.edu>
.. moduleauthor:: Thomas G. Dimiduk <tdimiduk@physics.harvard.edu>
"""

# TODO:
# 2. Once sphere_coords is removed and everything is in the same format,
#    you can remove the type checking from is_detector_view_point_or_flat
# 3. Remove the type-checking in ScatteringTheory.
# 4. Make the private class method _transform_to_desired_coordinates
#    cylindrical coords for mielens.


from warnings import warn

import numpy as np
import xarray as xr

from holopy.core.math import find_transformation_function  # to_spherical
from holopy.core.holopy_object import HoloPyObject
from holopy.scattering.scatterer import Scatterers, Sphere
from holopy.scattering.errors import TheoryNotCompatibleError, MissingParameter
from holopy.core.metadata import (
    vector, illumination, flat, update_metadata, clean_concat)
from holopy.core.utils import dict_without, updated, ensure_array
try:
    from holopy.scattering.theory.mie_f import mieangfuncs
except ImportError:
    pass


def get_wavevec_from(schema):
    return 2 * np.pi / (schema.illum_wavelen / schema.medium_index)


class ScatteringTheory(HoloPyObject):
    """
    Defines common interface for all scattering theories.

    Notes
    -----
    A subclasses that do the work of computing scattering should do it
    by implementing _raw_fields and/or _raw_scat_matrs and (optionally)
    _raw_cross_sections. _raw_cross_sections is needed only for
    calc_cross_sections. Either of _raw_fields or _raw_scat_matrs will
    give you calc_holo, calc_field, and calc_intensity. Obviously
    calc_scat_matrix will only work if you implement _raw_cross_sections.
    So the simplest thing is to just implement _raw_scat_matrs. You only
    need to do _raw_fields there is a way to compute it more efficently
    and you care about that speed, or if it is easier and you don't care
    about matrices.
    """
    desired_coordinate_system = 'spherical'

    def calculate_scattered_field(self, scatterer, schema):
        """
        Implemented in derived classes only.

        Parameters
        ----------
        scatterer : :mod:`.scatterer` object
            (possibly composite) scatterer for which to compute scattering

        Returns
        -------
        e_field : :mod:`.VectorGrid`
            scattered electric field
        """
        if scatterer.center is None:
            raise MissingParameter("center")
        is_multicolor_hologram = len(ensure_array(schema.illum_wavelen)) > 1
        field = (
            self._calculate_multiple_color_scattered_field(scatterer, schema)
            if is_multicolor_hologram else
            self._calculate_single_color_scattered_field(scatterer, schema))
        return field

    def _calculate_multiple_color_scattered_field(self, scatterer, schema):
        field = []
        for illum in schema.illum_wavelen.illumination.values:
            this_schema = update_metadata(
                schema,
                illum_wavelen=ensure_array(
                    schema.illum_wavelen.sel(illumination=illum).values)[0],
                illum_polarization=ensure_array(
                    schema.illum_polarization.sel(illumination=illum).values))
            this_field = self._calculate_single_color_scattered_field(
                scatterer.select({illumination: illum}), this_schema)
            field.append(this_field)
        field = clean_concat(field, dim=schema.illum_wavelen.illumination)
        return field

    def _calculate_scattered_field_from_superposition(
            self, scatterers, schema):
        field = self._calculate_single_color_scattered_field(
            scatterers[0], schema)
        for s in scatterers[1:]:
            field += self._calculate_single_color_scattered_field(s, schema)
        return field

    def _calculate_single_color_scattered_field(self, scatterer, schema):
        if self._can_handle(scatterer):
            field = self._get_field_from(scatterer, schema)
        elif isinstance(scatterer, Scatterers):
            field = self._calculate_scattered_field_from_superposition(
                scatterer.get_component_list(), schema)
        else:
            raise TheoryNotCompatibleError(self, scatterer)
        return self._pack_field_into_xarray(field, schema)

    def _get_field_from(self, scatterer, schema):
        """
        Parameters
        ----------
        scatterer
        schema : xarray
            (it's always passed in as an xarray)

        Returns
        -------
        raveled fields, shape (npoints = nx*ny = schema.shape.prod(), 3)
        """
        wavevector = get_wavevec_from(schema)
        positions = self._transform_to_desired_coordinates(
            schema, scatterer.center, wavevec=wavevector)
        scattered_field = np.transpose(
            self._raw_fields(
                positions,
                scatterer,
                medium_wavevec=wavevector,
                medium_index=schema.medium_index,
                illum_polarization=schema.illum_polarization)
            )
        phase = np.exp(-1j * wavevector * scatterer.center[2])
        scattered_field *= phase
        return scattered_field

    def _pack_field_into_xarray(self, scattered_field, schema):
        """Packs the numpy.ndarray, shape (N, 3) ``scattered_field`` into
        an xr.DataArray, shape (N, 3). This function needs to pack the
        fields [flat or point, vector], with the coordinates the
        same as that of the schema."""
        flattened_schema = flat(schema)  # now either point or flat
        point_or_flat = self._is_detector_view_point_or_flat(flattened_schema)
        coords = {
            key: (point_or_flat, val.values)
            for key, val in flattened_schema[point_or_flat].coords.items()}

        coords.update(
            {point_or_flat: flattened_schema[point_or_flat],
             vector: ['x', 'y', 'z']})
        scattered_field = xr.DataArray(
            scattered_field, dims=[point_or_flat, vector], coords=coords,
            attrs=schema.attrs)
        return scattered_field

    def _pack_scattering_matrix_into_xarray(
            self, scat_matrs, r_theta_phi, schema):
        flattened_schema = flat(schema)
        point_or_flat = self._is_detector_view_point_or_flat(flattened_schema)
        dims = [point_or_flat, 'Epar', 'Eperp']

        coords = {point_or_flat: flattened_schema.coords[point_or_flat]}
        coords.update({
            'r': (point_or_flat, r_theta_phi[ 0]),
            'theta': (point_or_flat, r_theta_phi[ 1]),
            'phi': (point_or_flat, r_theta_phi[ 2]),
            'Epar': ['S2', 'S3'],
            'Eperp': ['S4', 'S1'],
            })

        packed = xr.DataArray(
            scat_matrs, dims=dims, coords=coords, attrs=schema.attrs)
        return packed

    def calculate_cross_sections(
            self, scatterer, medium_wavevec, medium_index, illum_polarization):
        raw_sections = self._raw_cross_sections(
            scatterer=scatterer, medium_wavevec=medium_wavevec,
            medium_index=medium_index, illum_polarization=illum_polarization)
        return xr.DataArray(raw_sections, dims=['cross_section'],
                            coords={'cross_section':
                                ['scattering', 'absorbtion',
                                 'extinction', 'assymetry']})

    def calculate_scattering_matrix(self, scatterer, schema):
        """
        Compute scattering matrices for scatterer

        Parameters
        ----------
        scatterer : :mod:`holopy.scattering.scatterer` object
            (possibly composite) scatterer for which to compute scattering

        Returns
        -------
        scat_matr : :mod:`.Marray`
            Scattering matrices at specified positions

        Notes
        -----
        calc_* functions can be called on either a theory class or a
        theory object. If called on a theory class, they use a default
        theory object which is correct for the vast majority of
        situations. You only need to instantiate a theory object if it
        has adjustable parameters and you want to use non-default values.
        """
        positions = self._transform_to_desired_coordinates(
            schema, scatterer.center)
        scat_matrs = self._raw_scat_matrs(
            scatterer, positions, medium_wavevec=get_wavevec_from(schema),
            medium_index=schema.medium_index)
        return self._pack_scattering_matrix_into_xarray(
            scat_matrs, positions, schema)

    def _raw_fields(self, pos, scatterer, medium_wavevec, medium_index,
                    illum_polarization):
        scat_matr = self._raw_scat_matrs(
            scatterer, pos, medium_wavevec=medium_wavevec,
            medium_index=medium_index)

        fields = np.zeros_like(pos.T, dtype=np.array(scat_matr).dtype)
        for i, point in enumerate(pos.T):
            kr, theta, phi = point
            escat_sph = mieangfuncs.calc_scat_field(
                kr, phi, scat_matr[i], illum_polarization.values[:2])
            fields[i] = mieangfuncs.fieldstocart(escat_sph, theta, phi)
        return fields.T

    @classmethod
    def _is_detector_view_point_or_flat(cls, detector_view):
        detector_dims = (
            detector_view.dims if isinstance(detector_view, xr.DataArray)
            else detector_view)
        if 'flat' in detector_dims:
            point_or_flat = 'flat'
        elif 'point' in detector_dims:
            point_or_flat = 'point'
        else:
            msg = ("xarray `detector_view` is not in the form of a 1D list " +
                   "of coordinates. Call ``flat`` first.")
            raise ValueError(msg)
        return point_or_flat

    @classmethod
    def _transform_to_desired_coordinates(cls, detector, origin, wavevec=1):
        if hasattr(detector, 'theta') and hasattr(detector, 'phi'):
            original_coordinate_system = 'spherical'
            original_coordinate_values = [
                (detector.r.values * wavevec if hasattr(detector, 'r')
                    else np.full(detector.theta.values.shape, np.inf)),
                detector.theta.values,
                detector.phi.values,
                ]
        else:
            original_coordinate_system = 'cartesian'
            f = flat(detector)  # 1.6 ms
            original_coordinate_values = [
                wavevec * (f.x.values - origin[0]),
                wavevec * (f.y.values - origin[1]),
                wavevec * (origin[2] - f.z.values),
                # z is defined opposite light propagation, so we invert
                ]
        method = find_transformation_function(
            original_coordinate_system,
            cls.desired_coordinate_system)
        return method(original_coordinate_values)

