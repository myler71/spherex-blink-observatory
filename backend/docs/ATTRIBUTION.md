# Data, Archive & Library Attribution (`docs/ATTRIBUTION.md`)

## Astronomical Data & Archives

1. **NASA/IPAC IRSA — SPHEREx (DR1, QR3, QR2)**
   - **DOIs:** DR1 Spectral Images `10.26131/IRSA678`, DR1 All-Sky Cube `10.26131/IRSA679`, QR3 `10.26131/IRSA662`, QR2 `10.26131/IRSA652`
   - **Acknowledgement:** "This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration."
   - **Canonical References:** Bock et al. (2026); Akeson et al. (2026); Korngut et al. (2026); Crill et al. (2025).

2. **ESA Gaia Data Release 3 (Gaia DR3)**
   - **Source:** `https://gea.esac.esa.int/tap-server/tap/sync`
   - **Acknowledgement:** "This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions, in particular the institutions participating in the Gaia Multilateral Agreement." (Gaia Collaboration et al. 2016, 2023).

3. **NASA/IPAC IRSA — AllWISE**
   - **Source:** `allwise_p3as_psd` via `https://irsa.ipac.caltech.edu/TAP/sync`
   - **Acknowledgement:** "This publication makes use of data products from the Wide-field Infrared Survey Explorer, which is a joint project of the University of California, Los Angeles, and the Jet Propulsion Laboratory/California Institute of Technology, and NEOWISE, which is a project of the Jet Propulsion Laboratory/California Institute of Technology. WISE and NEOWISE are funded by the National Aeronautics and Space Administration." (Wright et al. 2010; Cutri et al. 2013).

4. **CDS — SIMBAD & VizieR**
   - **Sources:** `https://simbad.cds.unistra.fr` / `https://simbad.harvard.edu`, `https://vizier.cds.unistra.fr` / `https://vizier.cfa.harvard.edu`
   - **Acknowledgement:** "This research has made use of the SIMBAD database and the VizieR catalogue access tool, CDS, Strasbourg, France." (Wenger et al. 2000; Ochsenbein et al. 2000).

5. **NASA/IPAC Extragalactic Database (NED)**
   - **Acknowledgement:** "This research has made use of the NASA/IPAC Extragalactic Database (NED), which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology."

6. **CSA / CADC — NEOSSat**
   - **Source:** `https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync` (`collection = 'NEOSSAT'`)
   - **Acknowledgement:** "This research used the facilities of the Canadian Astronomy Data Centre operated by the National Research Council of Canada with the support of the Canadian Space Agency, including NEOSSat observations."

7. **JPL Horizons**
   - **Source:** `https://ssd.jpl.nasa.gov/api/horizons.api`
   - **Acknowledgement:** "Ephemerides provided by the Solar System Dynamics Group, Jet Propulsion Laboratory, California Institute of Technology."

8. **Harvard/SAO — NASA Astrophysics Data System (ADS)**
   - **Source:** `https://api.adsabs.harvard.edu/v1/search/query`
   - **Acknowledgement:** "This research has made use of NASA's Astrophysics Data System Bibliographic Services."

9. **WiseView Inspiration**
   - **Reference:** Caselden et al. (2018), `http://byw.tools/wiseview` (Backyard Worlds: Planet 9).

## Open-Source Software Libraries

- **FastAPI** (MIT), **Uvicorn** (BSD-3), **Pydantic / pydantic-settings** (MIT)
- **NumPy** (BSD-3), **SciPy** (BSD-3)
- **Astropy** (BSD-3), **Astroquery** (BSD-3), **PyVO** (BSD-3), **Reproject** (BSD-3), **Photutils** (BSD-3), **SEP / sep-pjw** (BSD-3 / LGPL-3 / MIT)
- **LangGraph / LangChain** (MIT), **SQLAlchemy** (MIT), **psycopg** (LGPL-3), **pgvector** (PostgreSQL), **Redis-py** (MIT), **HTTPX** (BSD-3)
