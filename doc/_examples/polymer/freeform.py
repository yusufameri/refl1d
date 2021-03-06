# Attached please find two data sets for a tethered  approximately 10 nm thick
# deuterated polystyrene chains in deuterated and hydrogenated toluene.
# 10 nm thickness is for dry conditions and I am assuming these chains will
# swell to 14-18 nm thickness once they are in toluene.
#    10ndt is for deuterated toluene case
#    10nht is for hydrogenated toluene case
# I also have to tell you that these chains are bound to the substrate by
# using an initiator layer between substrate and brush chains. So in your
# model you should have a silicon layer, silicon oxide layer, initiator layer
# which is mostly hydrocarbon and scattering length density should be between
# 0 and 1.5 depending on how much solvent is in the layer. Then you have the
# swollen brush chains and at the end bulk solvent. When we do these swelling
# measurements beam penetrate the system from the silicon side and the bottom
# layer is deuterated or hydrogenated toluene.
import sys
from periodictable import formula
from refl1d.names import *
from copy import copy
import numpy
from numpy import cos, log, exp, arange, pi, inf


## =============== Models ======================

## Materials composition based approach.
#deutrated_density = formula("C6H5C2D3").mass/formula("C6H5C2H3").mass
#D_polystyrene = Material("C6H5C2D3", density=0.909*deuterated_density)
#SiOx = Material("SiO2", density=2.634)
#alkane = Material("C8H18",density=0.703)  # Octane formula and density
#deutrated_density = formula("C6H5CD3").mass/formula("C6H5CH3").mass
#H_toluene = Material("C6H5CH3", density=0.8669)
#D_toluene = Material("C6H5CD3", density=0.8669*deuterated_density)
#H_initiator = Compound.byvolume(alkane, H_toluene, 10)
#D_initiator = Compound.byvolume(alkane, D_toluene, H_initiator.fraction[0])



### Deuterated toluene solvent system
D_polystyrene = SLD(name="D-PS",rho=6.2)
SiOx = SLD(name="SiOx",rho=3.47)
D_toluene = SLD(name="D-toluene",rho=5.66)
D_initiator = SLD(name="D-initiator",rho=1.5)
H_toluene = SLD(name="H-toluene",rho=0.94)
H_initiator = SLD(name="H-initiator",rho=0)

n=5
D_polymer_layer = FreeInterface(below=D_polystyrene,above=D_toluene,
                                dz=[1]*n,dp=[1]*n)

# Stack materials into samples
# Note: only need D_toluene to compute Fresnel-normalized reflectivity --- should fix
# this later so that we can use a pure freeform layer on top.
D = silicon(0,5) | SiOx(100,5) | D_initiator(100,20) | D_polymer_layer(1000,0) | D_toluene

### Undeuterated toluene solvent system
H_polymer_layer = copy(D_polymer_layer)  # Share tethered polymer parameters...
H_polymer_layer.above = H_toluene      # ... but use different solvent
H = silicon | SiOx | H_initiator | H_polymer_layer | H_toluene
for i,_ in enumerate(D):
    H[i].thickness = D[i].thickness
    H[i].interface = D[i].interface


# ================= Fitting parameters ==================

for i in 0, 1, 2:
    D[i].interface.range(0,100)
D[1].thickness.range(0,200)
D[2].thickness.range(0,200)
D_polystyrene.rho.range(6.2,6.5)
SiOx.rho.range(2.07,4.16) # Si - SiO2
#SiOx.rho.pmp(10) # SiOx +/- 10%
D_toluene.rho.pmp(5)
D_initiator.rho.range(0,1.5)
for p in D_polymer_layer.dz[1:]:
    p.range(0,1)

## Undeuterated system adds two extra parameters
H_toluene.rho.pmp(5)
H_initiator.rho.range(-0.5,0.5)



# ================= Data files ===========================
instrument = NCNR.NG7(Qlo=0.005, slits_at_Qlo=0.075)
D_probe = instrument.load('10ndt001.refl', back_reflectivity=True)
H_probe = instrument.load('10nht001.refl', back_reflectivity=True)


# Join models and data
D_model = Experiment(sample=D, probe=D_probe)
H_model = Experiment(sample=H, probe=H_probe)
models = D_model, H_model

problem = MultiFitProblem(models=models)
