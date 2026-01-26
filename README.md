# Urban GNSS Risk Assessment: Reproducible Research Package

This repository contains the source code and data processing pipeline for the paper:
**"Urban GNSS Risk Assessment Using High-Definition 3D City Models: Validating the 'Building-First' Hypothesis"**
(Accepted at Pacific PNT 2026)

## 📌 Overview
This study empirically evaluates GNSS signal degradation in dense urban environments (Shibuya, Tokyo). We demonstrate that standard "Building-Only" 3D maps fail to detect critical overhead hazards, such as highway viaducts.

### The Problem: Invisible Hazards
Standard maps overlook overhead infrastructure. As shown below, **Site A11** is located directly beneath a highway, yet building-only models classify it as "Open Sky."

![Site A11 Viaduct](docs/images/site_a11_viaduct.jpg)
*Figure: Site A11 located under a highway viaduct. Building-only models fail to detect this risk.*

### Our Solution
We propose a **Hybrid Override Logic** that integrates infrastructure data, significantly improving risk prediction accuracy (AUC 0.68 -> 0.89).

## 📂 Repository Structure

- `data/`: Processed datasets (Raw GNSS logs are available upon request due to size).
- `qgis_scripts/`: Python scripts for QGIS to process PLATEAU 3D data and perform site selection.
- `src/`: Main analysis pipelines.
    - `00_utils`: GNSS log parsers and adapters.
    - `01_baseline_phase1`: Standard building-centric risk assessment.
    - `02_proposed_phase2`: Proposed hybrid model (Building + Infrastructure).
    - `03_analysis`: Visualization scripts for paper figures (ROC curves, Maps).
- `docs/`: Supplementary materials and images.

## 📡 Data Collection Protocol
The raw GNSS logs in `data/raw/` were collected under the following strict conditions:

- **Device**: Google Pixel 8 (Android 16)
- **Software**: Google GNSS Logger v3.0.0.1
- **Mounting**: Tripod-mounted at **1.5m height** (Screen facing zenith)
- **Constellations**: GPS (L1/L5), QZSS (L1/L5), Galileo (E1/E5a), BeiDou, GLONASS
- **Duration**: 5 minutes 30 seconds per site
- **Dates**: January 10, 11, 12, and 14, 2026 (11:00 - 14:00 JST)
- **Environment**: 45 stratified sites (Open / Street / Alley) within a **500m x 500m Area of Interest (AOI)** in Shibuya, Tokyo.

![Experimental Setup](docs/images/experiment_setup.jpg)
*Figure: Field measurement setup using a tripod.*

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- **QGIS 3.40 LTR** (Required for Step 0: Data Preprocessing)

### Installation
```bash
git clone [https://github.com/0319-2004/PacificPNT_Reproducible.git](https://github.com/0319-2004/PacificPNT_Reproducible.git)
cd PacificPNT_Reproducible
pip install -r requirements.txt
