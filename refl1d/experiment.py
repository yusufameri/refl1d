# This program is in the public domain
# Author: Paul Kienzle

"""
Experiment definition

An experiment combines the sample definition with a measurement probe
to create a fittable reflectometry model.
"""
from __future__ import division, print_function

from math import pi, log10, floor
import os
import traceback

import numpy
from bumps import parameter

from .reflectivity import reflectivity_amplitude as reflamp
from .reflectivity import magnetic_amplitude as reflmag
#print("Using pure python reflectivity calculator")
#from .abeles import refl as reflamp
from . import material, profile


def plot_sample(sample, instrument=None, roughness_limit=0):
    """
    Quick plot of a reflectivity sample and the corresponding reflectivity.
    """
    if instrument == None:
        from .probe import NeutronProbe
        probe = NeutronProbe(T=numpy.arange(0,5,0.05), L=5)
    else:
        probe = instrument.simulate()
    experiment = Experiment(sample=sample, probe=probe,
                            roughness_limit=roughness_limit)
    experiment.plot()

class ExperimentBase(object):
    def format_parameters(self):
        p = self.parameters()
        print(parameter.format(p))

    def update_composition(self):
        """
        When the model composition has changed, we need to lookup the
        scattering factors for the new model.  This is only needed
        when an existing chemical formula is modified; new and
        deleted formulas will be handled automatically.
        """
        self._probe_cache.reset()
        self.update()

    def is_reset(self):
        """
        Returns True if a model reset was triggered.
        """
        return self._cache == {}

    def update(self):
        """
        Called when any parameter in the model is changed.

        This signals that the entire model needs to be recalculated.
        """
        # if we wanted to be particularly clever we could predefine
        # the optical matrices and only adjust those that have changed
        # as the result of a parameter changing.   More trouble than it
        # is worth, methinks.
        #print("reseting calculation")
        self._cache = {}

    def residuals(self):
        if 'residuals' not in self._cache:
            if ((self.probe.polarized
                 and all(x is None or x.R is None for x in self.probe.xs))
                or (not self.probe.polarized and self.probe.R is None)):
                resid = numpy.zeros(0)
            else:
                QR = self.reflectivity()
                if self.probe.polarized:
                    resid = numpy.hstack([(xs.R - QRi[1])/xs.dR
                                          for xs,QRi in zip(self.probe.xs, QR)
                                          if xs is not None])
                else:
                    resid = (self.probe.R - QR[1])/self.probe.dR
            self._cache['residuals'] = resid
            #print(("%12s "*4)%("Q","R","dR","Rtheory"))
            #print("\n".join(("%12.6e "*4)%el for el in zip(QR[0],self.probe.R,self.probe.dR,QR[1]))
            #print("resid",numpy.sum(resid**2)/2)

        return self._cache['residuals']

    def numpoints(self):
        if self.probe.polarized:
            return sum(len(xs.Q) for xs in self.probe.xs if xs is not None)
        else:
            return len(self.probe.Q) if self.probe.Q is not None else 0

    def nllf(self):
        """
        Return the -log(P(data|model)).

        Using the assumption that data uncertainty is uncorrelated, with
        measurements normally distributed with mean R and variance dR**2,
        this is just sum( resid**2/2 + log(2*pi*dR**2)/2 ).

        The current version drops the constant term, sum(log(2*pi*dR**2)/2).
        """
        #if 'nllf_scale' not in self._cache:
        #    if self.probe.dR is None:
        #        raise ValueError("No data from which to calculate nllf")
        #    self._cache['nllf_scale'] = numpy.sum(numpy.log(2*pi*self.probe.dR**2))
        # TODO: add sigma^2 effects back into nllf; only needs to be calculated
        # when dR changes, so maybe it belongs in probe.
        return 0.5*numpy.sum(self.residuals()**2) # + self._cache['nllf_scale']

    def plot_reflectivity(self, show_resolution=False,
                          view=None, plot_shift=None):

        QR = self.reflectivity()
        self.probe.plot(theory=QR,
                        substrate=self._substrate, surface=self._surface,
                        view=view, plot_shift=plot_shift)

        if show_resolution:
            import pylab
            QR = self.reflectivity(resolution=False)
            if self.probe.polarized:
                # Should be four pairs
                for Q,R in QR:
                    pylab.plot(Q,R,':g',hold=True)
            else:
                Q,R = QR
                pylab.plot(Q,R,':g',hold=True)


    def plot(self, plot_shift=None, profile_shift=None):
        import pylab
        pylab.subplot(211)
        self.plot_reflectivity(plot_shift=plot_shift)
        pylab.subplot(212)
        self.plot_profile(plot_shift=profile_shift)

    def resynth_data(self):
        """Resynthesize data with noise from the uncertainty estimates."""
        self.probe.resynth_data()
    def restore_data(self):
        """Restore original data after resynthesis."""
        self.probe.restore_data()
    def write_data(self, filename, **kw):
        """Save simulated data to a file"""
        self.probe.write_data(filename, **kw)
    def simulate_data(self, noise=2):
        """
        Simulate a random data set for the model

        **Parameters:**

        *noise* = 2 : float | %
            Percentage noise to add to the data.
        """
        theory = self.reflectivity(resolution=True)
        self.probe.simulate_data(theory, noise=noise)
    def _set_name(self, name):
        self._name = name
    def _get_name(self):
        return self._name if self._name else self.probe.name
    name = property(_get_name, _set_name)

    def save(self, basename):
        self.save_profile(basename)
        self.save_staj(basename)
        self.save_refl(basename)

    def save_profile(self, basename):
        if self.ismagnetic:
            self._save_magnetic(basename)
        else:
            self._save_nonmagnetic(basename)

    def _save_magnetic(self, basename):
        # Slabs
        A = numpy.array(self.magnetic_slabs())
        fid = open(basename+"-slabs.dat","w")
        fid.write("# %17s %20s %20s %20s %20s\n"
                  %("thickness (A)", "rho (1e-6/A^2)", "irho (1e-6/A^2)",
                    "rhoM (1e-6/A^2)", "theta (degrees)"))
        numpy.savetxt(fid, A.T, fmt="%20.15g")
        fid.close()

        # Step profile
        A = numpy.array(self.magnetic_profile())
        fid = open(basename+"-steps.dat","w")
        fid.write("# %10s %12s %12s %12s %12s\n"
                  %("z (A)", "rho (1e-6/A2)", "irho (1e-6/A2)",
                    "rhoM (1e-6/A2)", "theta (degrees)"))
        numpy.savetxt(fid, A.T, fmt="%12.8f")
        fid.close()

    def _save_nonmagnetic(self, basename):
        # Slabs
        A = numpy.array(self.slabs())
        fid = open(basename+"-slabs.dat","w")
        fid.write("# %17s %20s %20s %20s\n"
                  %("thickness (A)","interface (A)","rho (1e-6/A^2)",
                    "irho (1e-6/A^2)"))
        numpy.savetxt(fid, A.T, fmt="%20.15g")
        fid.close()

        # Step profile
        A = numpy.array(self.step_profile())
        fid = open(basename+"-steps.dat","w")
        fid.write("# %10s %20s %20s\n"
                  %("z (A)", "rho (1e-6/A2)", "irho (1e-6/A2)"))
        numpy.savetxt(fid, A.T, fmt="%12.8f")
        fid.close()

        # Smooth profile
        A = numpy.array(self.smooth_profile())
        fid = open(basename+"-profile.dat","w")
        fid.write("# %10s %12s %12s\n"
                  %("z (A)", "rho (1e-6/A2)", "irho (1e-6/A2)"))
        numpy.savetxt(fid, A.T, fmt="%12.8f")
        fid.close()

    def save_refl(self, basename):
        # Reflectivity
        theory = self.reflectivity()
        self.probe.save(filename=basename+"-refl.dat", theory=theory,
                        substrate=self._substrate, surface=self._surface)



class Experiment(ExperimentBase):
    """
    Theory calculator.  Associates sample with data, Sample plus data.
    Associate sample with measurement.

    The model calculator is specific to the particular measurement technique
    that was applied to the model.

    Measurement properties:

        *probe* is the measuring probe

    Sample properties:

        *sample* is the model sample
        *step_interfaces* use slabs to approximate gaussian interfaces
        *roughness_limit* limit the roughness based on layer thickness
        *dz* minimum step size for computed profile steps in Angstroms
        *dA* discretization condition for computed profiles

    If *step_interfaces* is True, then approximate the interface using
    microslabs with step size *dz*.  The microslabs extend throughout
    the whole profile, both the interfaces and the bulk; a value
    for *dA* should be specified to save computation time.  If False, then
    use the Nevot-Croce analytic expression for the interface between slabs.

    The *roughness_limit* value should be reasonably large (e.g., 2.5 or above)
    to make sure that the Nevot-Croce reflectivity calculation matches the
    calculation of the displayed profile.  Use a value of 0 if you want no
    limits on the roughness,  but be aware that the displayed profile may
    not reflect the actual scattering densities in the material.

    The *dz* step size sets the size of the slabs for non-uniform profiles.
    Using the relation d = 2 pi / Q_max,  we use a default step size of d/20
    rounded to two digits, with 5 |Ang| as the maximum default.  For
    simultaneous fitting you may want to set *dz* explicitly using to
    round(pi/Q_max/10,1) so that all models use the same step size.

    The *dA* condition measures the uncertainty in scattering materials
    allowed when combining the steps of a non-uniform profile into slabs.
    Specifically, the area of the box containing the minimum and the
    maximum of the non-uniform profile within the slab will be smaller
    than *dA*.  A *dA* of 10 gives coarse slabs.  If *dA* is not provided
    then each profile step forms its own slab.  The *dA* condition will
    also apply to the slab approximation to the interfaces.
    """
    profile_shift = 0
    def __init__(self, sample=None, probe=None, name=None,
                 roughness_limit=0, dz=None, dA=None,
                 step_interfaces=False, smoothness=None):
        # Note: smoothness ignored
        self.sample = sample
        self._substrate=self.sample[0].material
        self._surface=self.sample[-1].material
        self.roughness_limit = roughness_limit
        if dz is None:
            dz = nice((2*pi/probe.Q.max())/10)
            if dz > 5: dz = 5
        # TODO: probe and dz are mutually dependent
        self._slabs = profile.Microslabs(1, dz=dz)
        self.probe = probe
        self.dA = dA
        self.step_interfaces = step_interfaces
        self._cache = {}  # Cache calculated profiles/reflectivities
        self._name = name

    @property
    def probe(self):
        return self._probe

    @probe.setter
    def probe(self, probe):
        self._probe = probe
        self._probe_cache = material.ProbeCache(probe)
        self._slabs.nprobe = len(probe.unique_L) if probe.unique_L is not None else 1

    @property
    def dz(self):
        return self._slabs.dz

    @dz.setter
    def dz(self, value):
        self._slabs.dz = value

    @property
    def ismagnetic(self):
        slabs = self._render_slabs()
        return slabs.ismagnetic

    def parameters(self):
        return {'sample':self.sample.parameters(),
                'probe':self.probe.parameters(),
                }

    def _render_slabs(self):
        """
        Build a slab description of the model from the individual layers.
        """
        key = 'rendered'
        if key not in self._cache:
            self._slabs.clear()
            self.sample.render(self._probe_cache, self._slabs)
            self._slabs.finalize(step_interfaces=self.step_interfaces,
                                 dA=self.dA,
                                 roughness_limit=self.roughness_limit)
            self._cache[key] = True
        return self._slabs

    def _reflamp(self):
        #calc_q = self.probe.calc_Q
        #return calc_q,calc_q
        key = 'calc_r'
        if key not in self._cache:
            slabs = self._render_slabs()
            w = slabs.w
            rho,irho = slabs.rho, slabs.irho
            sigma = slabs.sigma
            #sigma = slabs.sigma
            calc_q = self.probe.calc_Q
            #print("calc Q", self.probe.calc_Q)
            if slabs.ismagnetic:
                rhoM, thetaM = slabs.rhoM, slabs.thetaM
                Aguide = self.probe.Aguide
                calc_r = reflmag(-calc_q/2, depth=w, rho=rho[0], irho=irho[0],
                                 rhoM=rhoM, thetaM=thetaM, Aguide=Aguide)
            else:
                calc_r = reflamp(-calc_q/2, depth=w, rho=rho, irho=irho,
                                 sigma=sigma)
            if False and numpy.isnan(calc_r).any():
                print("w %s",w)
                print("rho",rho)
                print("irho",irho)
                print("sigma",sigma)
                print("kz",self.probe.calc_Q/2)
                print("R",abs(calc_r**2))
                pars = parameter.unique(self.parameters())
                fitted = parameter.varying(pars)
                print(parameter.summarize(fitted))
                print("===")
            self._cache[key] = calc_q,calc_r
            #if numpy.isnan(calc_q).any(): print("calc_Q contains NaN")
            #if numpy.isnan(calc_r).any(): print("calc_r contains NaN")
        return self._cache[key]

    def amplitude(self, resolution=False):
        """
        Calculate reflectivity amplitude at the probe points.
        """
        key = ('amplitude',resolution)
        if key not in self._cache:
            calc_q,calc_r = self._reflamp()
            r_real = self.probe.apply_beam(calc_q, calc_r.real, resolution=resolution)
            r_imag = self.probe.apply_beam(calc_q, calc_r.imag, resolution=resolution)
            r = r_real + 1j*r_imag
            self._cache[key] = self.probe.Q, r
        return self._cache[key]

    def reflectivity(self, resolution=True):
        """
        Calculate predicted reflectivity.

        If *resolution* is true include resolution effects.
        """
        key = ('reflectivity',resolution)
        if key not in self._cache:
            Q, r = self._reflamp()
            R = _amplitude_to_magnitude(r,
                                        ismagnetic=self.ismagnetic,
                                        polarized=self.probe.polarized)
            res = self.probe.apply_beam(Q, R, resolution=resolution)
            self._cache[key] = res
        return self._cache[key]

    def smooth_profile(self,dz=0.1):
        """
        Return the scattering potential for the sample.

        If *dz* is not given, use *dz* = 0.1 A.
        """
        if self.step_interfaces:
            return self.step_profile()
        key = 'smooth_profile', dz
        if key not in self._cache:
            slabs = self._render_slabs()
            prof = slabs.smooth_profile(dz=dz)
            self._cache[key] = prof
        return self._cache[key]

    def step_profile(self):
        """
        Return the step scattering potential for the sample, ignoring
        interfaces.
        """
        key = 'step_profile'
        if key not in self._cache:
            slabs = self._render_slabs()
            prof = slabs.step_profile()
            self._cache[key] = prof
        return self._cache[key]

    def slabs(self):
        """
        Return the slab thickness, roughness, rho, irho for the
        rendered model.

        .. Note::
             Roughness is for the top of the layer.
        """
        slabs = self._render_slabs()
        return (slabs.w, numpy.hstack((slabs.sigma,0)),
                slabs.rho[0], slabs.irho[0])

    def magnetic_profile(self):
        """
        Return the nuclear and magnetic scattering potential for the sample.
        """
        key = 'magnetic_profile'
        if key not in self._cache:
            slabs = self._render_slabs()
            prof = slabs.magnetic_profile()
            self._cache[key] = prof
        return self._cache[key]

    def magnetic_slabs(self):
        slabs = self._render_slabs()
        return (slabs.w, slabs.rho[0], slabs.irho[0],
                slabs.rhoM, slabs.thetaM)

    def save_staj(self, basename):
        from .stajconvert import save_mlayer
        try:
            if self.probe.R is not None:
                datafile = getattr(self.probe, 'filename', basename+".refl")
            else:
                datafile = None
            save_mlayer(self, basename+".staj", datafile=datafile)
            probe = self.probe
            datafile = os.path.join(os.path.dirname(basename),os.path.basename(datafile))
            fid = open(datafile,"w")
            fid.write("# Q R dR\n")
            numpy.savetxt(fid, numpy.vstack((probe.Qo,probe.R,probe.dR)).T)
            fid.close()
        except:
            print("==== could not save staj file ====")
            traceback.print_exc()


    def plot_profile(self, plot_shift=None):
        import pylab
        from bumps.plotutil import auto_shift
        plot_shift = plot_shift if plot_shift is not None else Experiment.profile_shift
        trans = auto_shift(plot_shift)
        if self.ismagnetic:
            z,rho,irho,rhoM,thetaM = self.magnetic_profile()
            #rhoM_net = rhoM*numpy.cos(numpy.radians(thetaM))
            pylab.plot(z,rho,transform=trans)
            pylab.plot(z,irho,hold=True,transform=trans)
            pylab.plot(z,rhoM,hold=True,transform=trans)
            pylab.xlabel('depth (A)')
            pylab.ylabel('SLD (10^6 / A**2)')
            pylab.legend(['rho','irho','rhoM'])
            if (abs(thetaM-thetaM[0])>1e-3).any():
                ax = pylab.twinx()
                pylab.plot(z,thetaM,':k',hold=True,axes=ax,transform=trans)
                pylab.ylabel('magnetic angle (degrees)')
        else:
            z,rho,irho = self.step_profile()
            pylab.plot(z,rho,':g',z,irho,':b',transform=trans)
            z,rho,irho = self.smooth_profile()
            pylab.plot(z,rho,'-g',z,irho,'-b', hold=True,transform=trans)
            pylab.legend(['rho','irho'])
            pylab.xlabel('depth (A)')
            pylab.ylabel('SLD (10^6 / A**2)')


    def penalty(self):
        return self.sample.penalty()

class MixedExperiment(ExperimentBase):
    """
    Support composite sample reflectivity measurements.

    Sometimes the sample you are measuring is not uniform.
    For example, you may have one portion of you polymer
    brush sample where the brushes are close packed and able
    to stay upright, whereas a different section of the sample
    has the brushes lying flat.  Constructing two sample
    models, one with brushes upright and one with brushes
    flat, and adding the reflectivity incoherently, you can
    then fit the ratio of upright to flat.

    *samples* the layer stacks making up the models
    *ratio* a list of parameters, such as [3,1] for a 3:1 ratio
    *probe* the measurement to be fitted or simulated

    *coherent* is True if the length scale of the domains
    is less than the coherence length of the neutron, or false
    otherwise.

    Statistics such as the cost functions for the individual
    profiles can be accessed from the underlying experiments
    using composite.parts[i] for the various samples.
    """
    def __init__(self, samples=None, ratio=None, probe=None,
                 name=None, coherent=False, **kw):
        self.samples = samples
        self.probe = probe
        self.ratio = [parameter.Parameter.default(r, name="ratio %d"%i)
                      for i,r in enumerate(ratio)]
        self.parts = [Experiment(s,probe,**kw) for s in samples]
        self.coherent = coherent
        self._substrate=self.samples[0][0].material
        self._surface=self.samples[0][-1].material
        self._cache = {}
        self._name = name

    def update(self):
        self._cache = {}
        for p in self.parts: p.update()

    def parameters(self):
        return {'samples': [s.parameters() for s in self.samples],
                'ratio': self.ratio,
                'probe': self.probe.parameters(),
                } 

    def _reflamp(self):
        """
        Calculate the amplitude of the reflectivity...

        For an incoherent sum, we want to add the squares of the amplitudes,
        with a weighting specified by self.ratio, so the amplitudes
        are scaled by sqrt(self.ratio/total) so when they get squared and added
        the normalization is correct.

        For a coherent sum, just multiply by ratio/total.
        It all comes out in the wash.
        """
        total = sum(r.value for r in self.ratio)
        Qs,Rs = zip(*[p._reflamp() for p in self.parts])
        if self.coherent == False:
            Rs = [numpy.asarray(ri)*numpy.sqrt(ratio_i.value/total)
              for ri,ratio_i in zip(Rs,self.ratio)]
        else: # self.coherent == True
            Rs = [numpy.asarray(ri)*(ratio_i.value/total)
              for ri,ratio_i in zip(Rs,self.ratio)]
        #print("Rs",Rs)
        return Qs[0], Rs

    def amplitude(self, resolution=False):
        """
        """
        if self.coherent == False:
            raise TypeError("Cannot compute amplitude of system which is mixed incoherently")
        key = ('amplitude',resolution)
        if key not in self._cache:
            calc_Q, calc_R = self._reflamp()
            calc_R = numpy.sum(calc_R, axis=1)
            r_real = self.probe.apply_beam(calc_Q, calc_R.real, resolution=resolution)
            r_imag = self.probe.apply_beam(calc_Q, calc_R.imag, resolution=resolution)
            r = r_real + 1j*r_imag
            self._cache[key] = self.probe.Q, r
        return self._cache[key]


    def reflectivity(self, resolution=True):
        """
        Calculate predicted reflectivity.

        This will be the weighted sum of the reflectivity from the
        individual systems.  If coherent is set, then the coherent
        sum will be used, otherwise the incoherent sum will be used.

        If *resolution* is true include resolution effects.
        """
        key = ('reflectivity',resolution)
        if key not in self._cache:
            Q, r = self._reflamp()

            polarized = self.probe.polarized
            ismagnetic = any(p.ismagnetic for p in self.parts)

            # If any reflectivity is magnetic, make all reflectivity magnetic
            if ismagnetic:
                for i,p in enumerate(self.parts):
                    if not p.ismagnetic:
                        r[i] = _polarized_nonmagnetic(r[i])

            # Add the cross sections
            if self.coherent:
                r = numpy.sum(r,axis=0)
                R = _amplitude_to_magnitude(r, ismagnetic=ismagnetic,
                                            polarized=polarized)
            else:
                R = [_amplitude_to_magnitude(ri, ismagnetic=ismagnetic,
                                             polarized=polarized)
                     for ri in r]
                R = numpy.sum(R,axis=0)

            # Apply resolution
            res = self.probe.apply_beam(Q, R, resolution=resolution)
            self._cache[key] = res
        return self._cache[key]

    def plot_profile(self, plot_shift=None):
        import pylab
        f = numpy.array([r.value for r in self.ratio],'d')
        f /= numpy.sum(f)
        held = pylab.hold()
        for p in self.parts:
            p.plot_profile(plot_shift=plot_shift)
            pylab.hold(True)
        pylab.hold(held)

    def save_profile(self, basename):
        for i,p in enumerate(self.parts):
            p.save_profile("%s-%d"%(basename,i))

    def save_staj(self, basename):
        for i,p in enumerate(self.parts):
            p.save_staj("%s-%d"%(basename,i))

    def penalty(self):
        return sum(s.penalty() for s in self.samples)

def _polarized_nonmagnetic(r):
    """Convert nonmagnetic data to polarized representation.

    Polarized non-magnetic data repeats the reflectivity in the non spin flip
    channels and sets the spin flip channels to zero.
    """
    nsf = r
    sf = 0*r
    return [nsf, sf, sf, nsf]

def _nonpolarized_magnetic(R):
    """Convert magnetic reflectivity to unpolarized representation.

    Unpolarized magnetic data adds the cross-sections of the magnetic
    data incoherently and divides by two.
    """
    return reduce(numpy.add, R)/2

def _amplitude_to_magnitude(r, ismagnetic, polarized):
    """
    Compute the reflectivity magnitude
    """
    if ismagnetic:
        R = [abs(xs)**2 for xs in r]
        if not polarized: R = _nonpolarized_magnetic(R)
    else:
        R = abs(r)**2
        if polarized: R = _polarized_nonmagnetic(R)
    return R


def nice(v, digits = 2):
    """Fix v to a value with a given number of digits of precision"""
    if v == 0.: return v
    sign = v/abs(v)
    place = floor(log10(abs(v)))
    scale = 10**(place-(digits-1))
    return sign*floor(abs(v)/scale+0.5)*scale
