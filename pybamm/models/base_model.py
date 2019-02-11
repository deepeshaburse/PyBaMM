#
# Base model class
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals
import pybamm

import numbers


class BaseModel(object):
    """Base model class for other models to extend.

    Attributes
    ----------

    rhs: dict
        A dictionary that maps expressions (variables) to expressions that represent
        the rhs
    algebraic: dict
        A list of algebraic expressions that are assumed to equate to zero
    initial_conditions: dict
        A dictionary that maps expressions (variables) to expressions that represent
        the initial conditions for the state variables y
    initial_conditions_ydot: dict
        A dictionary that maps expressions (variables) to expressions that represent
        the initial conditions for the time derivative of y
    boundary_conditions: dict
        A dictionary that maps expressions (variables) to expressions that represent
        the boundary conditions
    variables: dict
        A dictionary that maps strings to expressions that represent
        the useful variables

    """

    def __init__(self):
        # Initialise empty model
        self._rhs = {}
        self._algebraic = []
        self._initial_conditions = {}
        self._initial_conditions_ydot = {}
        self._boundary_conditions = {}
        self._variables = {}
        self._concatenated_rhs = None
        self._concatenated_initial_conditions = None

        # Default parameter values, discretisation and solver
        self.default_parameter_values = pybamm.ParameterValues(
            "input/parameters/lithium-ion/parameters/LCO.csv"
        )

        self.default_geometry = pybamm.Geometry1DMacro()
        self.default_parameter_values.process_geometry(self.default_geometry)
        # provide mesh properties
        submesh_pts = {
            "negative electrode": {"x": 40},
            "separator": {"x": 25},
            "positive electrode": {"x": 35},
        }
        submesh_types = {
            "negative electrode": pybamm.Uniform1DSubMesh,
            "separator": pybamm.Uniform1DSubMesh,
            "positive electrode": pybamm.Uniform1DSubMesh,
        }

        mesh_type = pybamm.Mesh

        self.default_discretisation = pybamm.FiniteVolumeDiscretisation(
            mesh_type, submesh_pts, submesh_types
        )
        self.default_solver = pybamm.ScipySolver(method="RK45")

    def _set_dict(self, dict, name):
        """
        Convert any scalar equations in dict to 'pybamm.Scalar'
        and check that domains are consistent
        """
        # Convert any numbers to a pybamm.Scalar
        for var, eqn in dict.items():
            if isinstance(eqn, numbers.Number):
                dict[var] = pybamm.Scalar(eqn)

        if not all(
            [
                variable.domain == equation.domain or equation.domain == []
                for variable, equation in dict.items()
            ]
        ):
            raise pybamm.DomainError(
                """variable and equation in {} must have the same domain""".format(name)
            )

        return dict

    @property
    def rhs(self):
        return self._rhs

    @rhs.setter
    def rhs(self, rhs):
        self._rhs = self._set_dict(rhs, "rhs")

    @property
    def algebraic(self):
        return self._algebraic

    @algebraic.setter
    def algebraic(self, algebraic):
        self._algebraic = algebraic

    @property
    def initial_conditions(self):
        return self._initial_conditions

    @initial_conditions.setter
    def initial_conditions(self, initial_conditions):
        self._initial_conditions = self._set_dict(
            initial_conditions, "initial_conditions"
        )

    @property
    def initial_conditions_ydot(self):
        return self._initial_conditions_ydot

    @initial_conditions_ydot.setter
    def initial_conditions_ydot(self, initial_conditions):
        self._initial_conditions_ydot = self._set_dict(
            initial_conditions, "initial_conditions_ydot"
        )

    @property
    def boundary_conditions(self):
        return self._boundary_conditions

    @boundary_conditions.setter
    def boundary_conditions(self, boundary_conditions):
        # Convert any numbers to a pybamm.Scalar
        for var, bcs in boundary_conditions.items():
            for side, eqn in bcs.items():
                if isinstance(eqn, numbers.Number):
                    boundary_conditions[var][side] = pybamm.Scalar(eqn)

        self._boundary_conditions = boundary_conditions

    @property
    def variables(self):
        return self._variables

    @variables.setter
    def variables(self, variables):
        self._variables = variables

    @property
    def concatenated_rhs(self):
        return self._concatenated_rhs

    @concatenated_rhs.setter
    def concatenated_rhs(self, concatenated_rhs):
        self._concatenated_rhs = concatenated_rhs

    @property
    def concatenated_initial_conditions(self):
        return self._concatenated_initial_conditions

    @concatenated_initial_conditions.setter
    def concatenated_initial_conditions(self, concatenated_initial_conditions):
        self._concatenated_initial_conditions = concatenated_initial_conditions

    def __getitem__(self, key):
        return self.rhs[key]

    def update(self, *submodels):
        """
        Update model to add new physics from submodels

        Parameters
        ----------
        submodel : iterable of submodels (subclasses of :class:`pybamm.BaseModel`)
            The submodels from which to create new model
        """
        for submodel in submodels:
            # check for duplicates in keys
            vars = [var.id for var in submodel.rhs.keys()] + [
                var.id for var in self.rhs.keys()
            ]
            assert len(vars) == len(set(vars)), pybamm.ModelError("duplicate variables")

            # update dicts
            self._rhs.update(submodel.rhs)
            self._initial_conditions.update(submodel.initial_conditions)
            self._boundary_conditions.update(submodel.boundary_conditions)
            self._variables.update(submodel.variables)

    def check_well_posedness(self):
        """
        Check that the model is well-posed by executing the following tests:
        - All the variables that appear in the rhs and algebraic equations appear in
        the rhs keys, with leeway for exactly n variables where n is the number of
        algebraic equations. Overdetermined if more equations than variables,
        underdetermined if more variables than equations.
        - There is an initial condition in self.initial_conditions for each
        variable/equation pair in self.rhs
        - There are appropriate boundary conditions in self.boundary_conditions for each
        variable/equation pair in self.rhs
        """
        # Equations (differential and algebraic)
        # Get all the variables from differential and algebraic equations
        variable_ids_in_eqns = set()
        for eqn in list(self.rhs.values()) + self.algebraic:
            variable_ids_in_eqns.update(
                [x.id for x in eqn.pre_order() if isinstance(x, pybamm.Variable)]
            )
        # Get all variables ids from rhs keys
        variable_ids_in_keys = set([var.id for var in self.rhs.keys()])
        # Compare eqns and keys
        unaccounted_variables = variable_ids_in_eqns.difference(variable_ids_in_keys)
        # Count how many variables are not accounted for by algebraic equations
        n_extra_variables = len(unaccounted_variables) - len(self.algebraic)
        # Make sure n_extra_variables == 0
        if n_extra_variables > 0:
            raise pybamm.ModelError("model is underdetermined")
        elif n_extra_variables < 0:
            raise pybamm.ModelError("model is overdetermined")

        # Initial conditions
        for var in self.rhs.keys():
            if var not in self.initial_conditions.keys():
                raise pybamm.ModelError(
                    """no initial condition given for variable '{}'""".format(var)
                )

        # Boundary conditions
        for var, eqn in self.rhs.items():
            if eqn.has_spatial_derivatives():
                # Variable must be in at least one expression in the boundary condition
                # keys (to account for both Dirichlet and Neumann boundary conditions)
                if not any(
                    [
                        any([var.id == symbol.id for symbol in key.pre_order()])
                        for key in self.boundary_conditions.keys()
                    ]
                ):
                    raise pybamm.ModelError(
                        """
                        no boundary condition given for variable '{}'
                        with equation '{}'
                        """.format(
                            var, eqn
                        )
                    )