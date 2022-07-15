#
# Base class for particles
#
import pybamm


class BaseParticle(pybamm.BaseSubModel):
    """
    Base class for molar conservation in particles.

    Parameters
    ----------
    param : parameter class
        The parameters to use for this submodel
    domain : str
        The domain of the model either 'Negative' or 'Positive'
    options: dict
        A dictionary of options to be passed to the model.
        See :class:`pybamm.BaseBatteryModel`

    **Extends:** :class:`pybamm.BaseSubModel`
    """

    def __init__(self, param, domain, options=None):
        super().__init__(param, domain, options=options)
        # Read from options to see if we have a particle size distribution
        self.size_distribution = self.options["particle size"] == "distribution"

    def _get_effective_diffusivity(self, c, T):
        param = self.param
        domain = self.domain.lower()
        domain_param = self.domain_param

        # Get diffusivity
        D = domain_param.D(c, T)

        # Account for stress-induced diffusion by defining a multiplicative
        # "stress factor"
        stress_option = getattr(self.options, domain)["stress-induced diffusion"]

        if stress_option == "true":
            stress_factor = 1 + domain_param.theta * (c - domain_param.c_0) / (
                1 + param.Theta * T
            )
        else:
            stress_factor = 1

        return D * stress_factor

    def _get_standard_concentration_variables(
        self, c_s, c_s_xav=None, c_s_rav=None, c_s_av=None, c_s_surf=None
    ):
        """
        All particle submodels must provide the particle concentration as an argument
        to this method. Some submodels solve for quantities other than the concentration
        itself, for example the 'XAveragedFickianDiffusion' models solves for the
        x-averaged concentration. In such cases the variables being solved for (set in
        'get_fundamental_variables') must also be passed as keyword arguments. If not
        passed as keyword arguments, the various average concentrations and surface
        concentration are computed automatically from the particle concentration.
        """
        Domain = self.domain
        domain = Domain.lower()

        # Get surface concentration if not provided as fundamental variable to
        # solve for
        if c_s_surf is None:
            c_s_surf = pybamm.surf(c_s)
        c_s_surf_av = pybamm.x_average(c_s_surf)

        c_scale = self.domain_param.c_max

        # Get average concentration(s) if not provided as fundamental variable to
        # solve for
        if c_s_xav is None:
            c_s_xav = pybamm.x_average(c_s)
        if c_s_rav is None:
            c_s_rav = pybamm.r_average(c_s)
        if c_s_av is None:
            c_s_av = pybamm.r_average(c_s_xav)

        variables = {
            f"{Domain} particle concentration": c_s,
            f"{Domain} particle concentration [mol.m-3]": c_s * c_scale,
            f"{Domain} particle concentration [mol.m-3]": c_s * c_scale,
            "X-averaged " + f"{domain} particle concentration": c_s_xav,
            f"X-averaged {domain} particle concentration [mol.m-3]": c_s_xav * c_scale,
            f"R-averaged {domain} particle concentration": c_s_rav,
            f"R-averaged {domain} particle concentration [mol.m-3]": c_s_rav * c_scale,
            f"Average {domain} particle concentration": c_s_av,
            f"Average {domain} particle concentration [mol.m-3]": c_s_av * c_scale,
            f"{Domain} particle surface concentration": c_s_surf,
            f"{Domain} particle surface concentration [mol.m-3]": c_scale * c_s_surf,
            f"X-averaged {domain} particle surface concentration": c_s_surf_av,
            f"X-averaged {domain} particle surface "
            "concentration [mol.m-3]": c_scale * c_s_surf_av,
            f"{Domain} electrode extent of lithiation": c_s_rav,
            f"X-averaged {domain} electrode extent of lithiation": c_s_av,
            f"Minimum {domain} particle concentration": pybamm.min(c_s),
            f"Maximum {domain} particle concentration": pybamm.max(c_s),
            f"Minimum {domain} particle "
            "concentration [mol.m-3]": pybamm.min(c_s) * c_scale,
            f"Maximum {domain} particle "
            "concentration [mol.m-3]": pybamm.max(c_s) * c_scale,
            f"Minimum {domain} particle surface concentration": pybamm.min(c_s_surf),
            f"Maximum {domain} particle surface concentration": pybamm.max(c_s_surf),
            f"Minimum {domain} particle surface "
            "concentration [mol.m-3]": pybamm.min(c_s_surf) * c_scale,
            f"Maximum {domain} particle surface "
            "concentration [mol.m-3]": pybamm.max(c_s_surf) * c_scale,
        }

        return variables

    def _get_total_concentration_variables(self, variables):
        Domain = self.domain
        domain = Domain.lower()

        c_s_rav = variables[f"R-averaged {domain} particle concentration"]
        eps_s = variables[f"{Domain} electrode active material volume fraction"]
        eps_s_av = pybamm.x_average(eps_s)
        c_s_vol_av = pybamm.x_average(eps_s * c_s_rav) / eps_s_av
        c_scale = self.domain_param.c_max
        L = self.domain_param.L
        A = self.param.A_cc

        variables.update(
            {
                f"{Domain} electrode SOC": c_s_vol_av,
                f"{Domain} electrode volume-averaged concentration": c_s_vol_av,
                f"{Domain} electrode "
                "volume-averaged concentration [mol.m-3]": c_s_vol_av * c_scale,
                f"Total lithium in {domain} electrode "
                "[mol]": pybamm.yz_average(c_s_vol_av * eps_s_av) * c_scale * L * A,
            }
        )
        return variables

    def _get_standard_flux_variables(self, N_s):
        Domain = self.domain
        domain = Domain.lower()

        variables = {f"{Domain} particle flux": N_s}

        if isinstance(N_s, pybamm.Broadcast):
            N_s_xav = pybamm.x_average(N_s)
            variables.update({"X-averaged " + f"{domain} particle flux": N_s_xav})
        return variables

    def _get_distribution_variables(self, R):
        """
        Forms the particle-size distributions and mean radii given a spatial variable
        R. The domains of R will be different depending on the submodel, e.g. for the
        `SingleSizeDistribution` classes R does not have an "electrode" domain.
        """
        Domain = self.domain
        domain = Domain.lower()

        R_typ = self.domain_param.R_typ
        # Particle-size distribution (area-weighted)
        f_a_dist = self.domain_param.f_a_dist(R)

        # Ensure the distribution is normalised, irrespective of discretisation
        # or user input
        f_a_dist = f_a_dist / pybamm.Integral(f_a_dist, R)

        # Volume-weighted particle-size distribution
        f_v_dist = R * f_a_dist / pybamm.Integral(R * f_a_dist, R)

        # Number-based particle-size distribution
        f_num_dist = (f_a_dist / R ** 2) / pybamm.Integral(f_a_dist / R ** 2, R)

        # True mean radii and standard deviations, calculated from the f_a_dist that
        # was given
        R_num_mean = pybamm.Integral(R * f_num_dist, R)
        R_a_mean = pybamm.Integral(R * f_a_dist, R)
        R_v_mean = pybamm.Integral(R * f_v_dist, R)
        sd_num = pybamm.sqrt(pybamm.Integral((R - R_num_mean) ** 2 * f_num_dist, R))
        sd_a = pybamm.sqrt(pybamm.Integral((R - R_a_mean) ** 2 * f_a_dist, R))
        sd_v = pybamm.sqrt(pybamm.Integral((R - R_v_mean) ** 2 * f_v_dist, R))

        # X-average the means and standard deviations to give scalars
        # (to remove the "electrode" domain, if present)
        R_num_mean = pybamm.x_average(R_num_mean)
        R_a_mean = pybamm.x_average(R_a_mean)
        R_v_mean = pybamm.x_average(R_v_mean)
        sd_num = pybamm.x_average(sd_num)
        sd_a = pybamm.x_average(sd_a)
        sd_v = pybamm.x_average(sd_v)

        # X-averaged distributions, or broadcast
        if R.domains["secondary"] == [f"{domain} electrode"]:
            f_a_dist_xav = pybamm.x_average(f_a_dist)
            f_v_dist_xav = pybamm.x_average(f_v_dist)
            f_num_dist_xav = pybamm.x_average(f_num_dist)
        else:
            f_a_dist_xav = f_a_dist
            f_v_dist_xav = f_v_dist
            f_num_dist_xav = f_num_dist

            # broadcast
            f_a_dist = pybamm.SecondaryBroadcast(f_a_dist_xav, [f"{domain} electrode"])
            f_v_dist = pybamm.SecondaryBroadcast(f_v_dist_xav, [f"{domain} electrode"])
            f_num_dist = pybamm.SecondaryBroadcast(
                f_num_dist_xav, [f"{domain} electrode"]
            )

        variables = {
            f"{Domain} particle sizes": R,
            f"{Domain} particle sizes [m]": R * R_typ,
            f"{Domain} area-weighted particle-size" + " distribution": f_a_dist,
            f"{Domain} area-weighted particle-size"
            " distribution [m-1]": f_a_dist / R_typ,
            f"{Domain} volume-weighted particle-size" + " distribution": f_v_dist,
            f"{Domain} volume-weighted particle-size"
            " distribution [m-1]": f_v_dist / R_typ,
            f"{Domain} number-based particle-size" + " distribution": f_num_dist,
            f"{Domain} number-based particle-size"
            " distribution [m-1]": f_num_dist / R_typ,
            f"{Domain} area-weighted" + " mean particle radius": R_a_mean,
            f"{Domain} area-weighted" + " mean particle radius [m]": R_a_mean * R_typ,
            f"{Domain} volume-weighted" + " mean particle radius": R_v_mean,
            f"{Domain} volume-weighted" + " mean particle radius [m]": R_v_mean * R_typ,
            f"{Domain} number-based" + " mean particle radius": R_num_mean,
            f"{Domain} number-based" + " mean particle radius [m]": R_num_mean * R_typ,
            f"{Domain} area-weighted particle-size" + " standard deviation": sd_a,
            f"{Domain} area-weighted particle-size"
            " standard deviation [m]": sd_a * R_typ,
            f"{Domain} volume-weighted particle-size" + " standard deviation": sd_v,
            f"{Domain} volume-weighted particle-size"
            " standard deviation [m]": sd_v * R_typ,
            f"{Domain} number-based particle-size" + " standard deviation": sd_num,
            f"{Domain} number-based particle-size"
            " standard deviation [m]": sd_num * R_typ,
            # X-averaged distributions
            f"X-averaged {domain} area-weighted particle-size "
            "distribution": f_a_dist_xav,
            f"X-averaged {domain} area-weighted particle-size "
            "distribution [m-1]": f_a_dist_xav / R_typ,
            f"X-averaged {domain} volume-weighted particle-size "
            "distribution": f_v_dist_xav,
            f"X-averaged {domain} volume-weighted particle-size "
            "distribution [m-1]": f_v_dist_xav / R_typ,
            f"X-averaged {domain} number-based particle-size "
            "distribution": f_num_dist_xav,
            f"X-averaged {domain} number-based particle-size "
            "distribution [m-1]": f_num_dist_xav / R_typ,
        }

        return variables

    def _get_standard_concentration_distribution_variables(self, c_s):
        """
        Forms standard concentration variables that depend on particle size R given
        the fundamental concentration distribution variable c_s from the submodel.
        """
        Domain = self.domain
        domain = Domain.lower()

        c_scale = self.domain_param.c_max
        # Broadcast and x-average when necessary
        if c_s.domain == [f"{domain} particle size"] and c_s.domains["secondary"] != [
            f"{domain} electrode"
        ]:
            # X-avg concentration distribution
            c_s_xav_distribution = pybamm.PrimaryBroadcast(c_s, [f"{domain} particle"])

            # Surface concentration distribution variables
            c_s_surf_xav_distribution = c_s
            c_s_surf_distribution = pybamm.SecondaryBroadcast(
                c_s_surf_xav_distribution, [f"{domain} electrode"]
            )

            # Concentration distribution in all domains.
            c_s_distribution = pybamm.PrimaryBroadcast(
                c_s_surf_distribution, [f"{domain} particle"]
            )
        elif c_s.domain == [f"{domain} particle"] and (
            c_s.domains["tertiary"] != [f"{domain} electrode"]
        ):
            # X-avg concentration distribution
            c_s_xav_distribution = c_s

            # Surface concentration distribution variables
            c_s_surf_xav_distribution = pybamm.surf(c_s_xav_distribution)
            c_s_surf_distribution = pybamm.SecondaryBroadcast(
                c_s_surf_xav_distribution, [f"{domain} electrode"]
            )

            # Concentration distribution in all domains.
            c_s_distribution = pybamm.TertiaryBroadcast(
                c_s_xav_distribution, [f"{domain} electrode"]
            )
        elif c_s.domain == [f"{domain} particle size"] and c_s.domains["secondary"] == [
            f"{domain} electrode"
        ]:
            # Surface concentration distribution variables
            c_s_surf_distribution = c_s
            c_s_surf_xav_distribution = pybamm.x_average(c_s)

            # X-avg concentration distribution
            c_s_xav_distribution = pybamm.PrimaryBroadcast(
                c_s_surf_xav_distribution, [f"{domain} particle"]
            )

            # Concentration distribution in all domains.
            c_s_distribution = pybamm.PrimaryBroadcast(
                c_s_surf_distribution, [f"{domain} particle"]
            )
        else:
            c_s_distribution = c_s

            # x-average the *tertiary* domain.
            # NOTE: not yet implemented. Make 0.5 everywhere
            c_s_xav_distribution = pybamm.FullBroadcast(
                0.5,
                [f"{domain} particle"],
                {
                    "secondary": f"{domain} particle size",
                    "tertiary": "current collector",
                },
            )

            # Surface concentration distribution variables
            c_s_surf_distribution = pybamm.surf(c_s)
            c_s_surf_xav_distribution = pybamm.x_average(c_s_surf_distribution)

        c_s_rav_distribution = pybamm.r_average(c_s_distribution)
        c_s_av_distribution = pybamm.x_average(c_s_rav_distribution)

        variables = {
            f"Average {domain} particle concentration "
            "distribution": c_s_av_distribution,
            f"{Domain} particle concentration distribution": c_s_distribution,
            f"{Domain} particle concentration distribution "
            "[mol.m-3]": c_scale * c_s_distribution,
            f"R-averaged {domain} particle concentration "
            "distribution": c_s_rav_distribution,
            f"R-averaged {domain} particle concentration distribution "
            "[mol.m-3]": c_scale * c_s_rav_distribution,
            f"X-averaged {domain} particle concentration "
            "distribution": c_s_xav_distribution,
            f"X-averaged {domain} particle concentration distribution "
            "[mol.m-3]": c_scale * c_s_xav_distribution,
            f"X-averaged {domain} particle surface concentration"
            " distribution": c_s_surf_xav_distribution,
            f"X-averaged {domain} particle surface concentration distribution "
            "[mol.m-3]": c_scale * c_s_surf_xav_distribution,
            f"{Domain} particle surface concentration"
            " distribution": c_s_surf_distribution,
            f"{Domain} particle surface concentration"
            " distribution [mol.m-3]": c_scale * c_s_surf_distribution,
        }
        return variables

    def _get_standard_flux_distribution_variables(self, N_s):
        """
        Forms standard flux variables that depend on particle size R given
        the flux variable N_s from the distribution submodel.
        """
        Domain = self.domain
        domain = Domain.lower()

        if [f"{domain} electrode"] in N_s.domains.values():
            # N_s depends on x

            N_s_distribution = N_s
            # x-av the *tertiary* domain
            # NOTE: not yet implemented. Fill with zeros instead
            N_s_xav_distribution = pybamm.FullBroadcast(
                0,
                [f"{domain} particle"],
                {
                    "secondary": f"{domain} particle size",
                    "tertiary": "current collector",
                },
            )
        elif isinstance(N_s, pybamm.Scalar):
            # N_s is a constant (zero), as in "fast" submodels

            N_s_distribution = pybamm.FullBroadcastToEdges(
                0,
                [f"{domain} particle"],
                auxiliary_domains={
                    "secondary": f"{domain} particle size",
                    "tertiary": f"{domain} electrode",
                    "quaternary": "current collector",
                },
            )
            N_s_xav_distribution = pybamm.FullBroadcastToEdges(
                0,
                [f"{domain} particle"],
                auxiliary_domains={
                    "secondary": f"{domain} particle size",
                    "tertiary": "current collector",
                },
            )
        else:
            N_s_xav_distribution = N_s
            N_s_distribution = pybamm.TertiaryBroadcast(N_s, [f"{domain} electrode"])

        variables = {
            f"X-averaged {domain} particle flux distribution": N_s_xav_distribution,
            f"{Domain} particle flux distribution": N_s_distribution,
        }

        return variables

    def _get_standard_diffusivity_variables(self, D_eff):
        Domain = self.domain
        domain = Domain.lower()
        D_scale = self.domain_param.D_typ_dim

        variables = {
            f"{Domain} effective diffusivity": D_eff,
            f"{Domain} effective diffusivity [m2.s-1]": D_eff * D_scale,
            f"X-averaged {domain} effective diffusivity": pybamm.x_average(D_eff),
            f"X-averaged {domain} effective diffusivity [m2.s-1]": pybamm.x_average(
                D_eff * D_scale
            ),
        }
        return variables

    def _get_standard_diffusivity_distribution_variables(self, D_eff):
        Domain = self.domain
        domain = Domain.lower()
        D_scale = self.domain_param.D_typ_dim

        variables = {
            f"{Domain} effective diffusivity distribution": D_eff,
            f"{Domain} effective diffusivity distribution[m2.s-1]": D_eff * D_scale,
            f"X-averaged {domain} effective diffusivity "
            "distribution": pybamm.x_average(D_eff),
            f"X-averaged {domain} effective diffusivity "
            "distribution[m2.s-1]": pybamm.x_average(D_eff * D_scale),
        }

        return variables
