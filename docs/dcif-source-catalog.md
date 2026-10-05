# DCIF Source Catalog

This file lists the DCIF resources currently present in `data/raw`, `data/normalized`, and
`data/structured/records.jsonl`. It is meant to make the assistant's source coverage easy to audit
when the DCIF website changes.

Current crawl contents:

- 1 DCIF overview HTML page.
- 43 linked PDF files.
- Structured records for overview sections, instruments, fees, staff, and linked guide/resource titles.

## Primary Overview Page

| Resource | Type | URL | What it contains |
| --- | --- | --- | --- |
| Department of Chemistry Instrumentation Facility (DCIF) – MIT Department of Chemistry | HTML | `https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/` | Main source page for facility overview, training requests, reservations, software, staff, fees, instrument inventory, instrument status, training guides, application notes, seminars, and guest lectures. |

## Structured Records Extracted From The Overview

These are not separate source files; they are deterministic records extracted from the overview page
and stored in `data/structured/records.jsonl`.

| Record group | Current records | What it contributes |
| --- | --- | --- |
| Overview sections | General Information; Training Requests; Instrument Reservations; Software | Facility access, automation/manual-use notes, training request process, reservation system, and software notes. |
| Mass Spectrometry instruments | GC/MS; AccuTOF-DART; Maldi-TOF; Q-TOF; QQQ; ICP-MS | Authoritative inventory and overview descriptions for DCIF mass spectrometry instruments. |
| NMR Spectroscopy instruments | Avance401; Neo402; Neo500; Neo501; JEOL502; Neo600 | Authoritative inventory and overview descriptions for DCIF NMR instruments. |
| Other instruments | Time-Domain NMR; FTIR; Polarimeter; HPLC; Poster Printing | Authoritative inventory and overview descriptions for other DCIF instruments and services. |
| Fee table entries | GCMS; LCMS; AccuTOF DART; Maldi-TOF; Q-TOF; QQQ; ICP-MS; AVIII 400; AVIII 401; Neo 402; Neo 500; Neo 501; JEOL 502; Neo 600; EPR; FTIR; Polarimeter; HPLC; Posters | MIT, non-profit, and commercial rates where listed on the overview page. |
| Staff records | General Lab Contact; Sarah Willis; Mohan Kumar; Bridget Becker; DCIF Stewards | Contact and staff information extracted from the overview page. |
| Guide/resource records | Training guides, application notes, quick-start guides, seminars, guest lectures, and advanced-topic links listed below | Link inventory used to connect questions to source PDFs and source categories. |

## Mass Spectrometry Resources

| Resource | Type | URL | Brief description |
| --- | --- | --- | --- |
| How to choose the best instrument | PDF | `https://www.dropbox.com/s/woioamusyz7fdym/Choosing%20the%20right%20API-MS%20sources.pdf?dl=1` | API-MS source selection guide for choosing among ionization/source options. |
| Quick start guide – LCMS | PDF | `https://www.dropbox.com/s/gpgpwnet56fst6t/Single%20Q%20LCMS_quick%20guide.pdf?dl=1` | Single quadrupole LCMS quick-start guide, including compatible solvents, sample preparation, acquisition, and data processing. |
| Quick start guide – GCMS | PDF | `https://www.dropbox.com/s/b5n26336nq018su/Agilent%20GCMS%20Quick%20Start%20Guide.pdf?dl=1` | Agilent GC/MS quick-start guide, including sample preparation, solvent restrictions, injection notes, acquisition, and data processing. |
| Quick start guide – AccuTOF | PDF | `https://www.dropbox.com/s/y7kzk4digfj1wts/Jeol%20Accu-ToF_05252022.pdf?dl=1` | JEOL AccuTOF quick-start guide, including sample preparation, DART/ESI operating steps, acquisition, and data handling. |
| Quick start guide – MALDI | PDF | `https://www.dropbox.com/s/nwcuoe0x6eudvwh/Bruker%20AutoFlex%20Speed%20Maldi_quick%20start.pdf?dl=1` | Bruker AutoFlex Speed MALDI quick-start guide, including sample/matrix preparation, plate spotting, acquisition, and data processing. |
| Quick start guide – Q-TOF | PDF | `https://www.dropbox.com/s/qd5o3ka61ugbrga/QToF-HR%20LCMS_2.pdf?dl=1` | Agilent Q-TOF LCMS quick-start guide, including compatible solvents, sample preparation, acquisition, processing, and shutdown. |
| Quick start guide – QQQ | PDF | `https://www.dropbox.com/s/ldqakg7fl5ag4y4/QqQ%20LCMS_Final.pdf?dl=1` | Agilent Ultivo QQQ LCMS quick-start guide, including compatible solvents, sample preparation, acquisition modes, processing, reporting, and shutdown. |
| Introduction to Mass Spectrometry – M. Kumar (2020-01-13) | PDF | `https://www.dropbox.com/s/bbzuostvteblojm/Kumar_2020-01-13_MS-1.pdf?dl=1` | Seminar slides introducing mass spectrometry concepts, instrumentation, and applications. |
| Introduction to Mass Spectrometry – M. Kumar (2020-01-15) | PDF | `https://www.dropbox.com/s/dwqhadxyzxo89qz/Kumar_2020-01-15_MS-2.pdf?dl=1` | Follow-up seminar slides on mass spectrometry concepts, workflows, and applications. |

## NMR Training And Instrument Use Resources

| Resource | Type | URL | Brief description |
| --- | --- | --- | --- |
| Bruker NMR Automation use | PDF | `https://www.dropbox.com/s/ollwcoamdm5wqat/Bruker_Automation_Training_Current.pdf?dl=1` | Introductory training for Bruker automation instruments using IconNMR and sample changers. |
| Bruker NMR Manual use | PDF | `https://www.dropbox.com/s/u8l8gvn5wrhcqxy/Bruker%20Manual%20Training.pdf?dl=1` | Introductory training for manual Bruker acquisition using TopSpin. |
| JEOL NMR use | PDF | `https://www.dropbox.com/s/kk1uh5brwwdai2f/Acquisition%20of%20Spectra%20on%20the%20JEOL%20Spectrometer.pdf?dl=1` | Guide for acquiring spectra on the JEOL spectrometer. |
| How to Acquire NMR Data | PDF | `https://www.dropbox.com/s/rykdg7jpcfmz86z/How_to_acquire.pdf?dl=1` | Introductory NMR data acquisition slides and workflow guidance. |
| How to Prepare NMR Samples | PDF | `https://www.dropbox.com/s/gsqkdltc3h1wl0w/How_to_sample.pdf?dl=1` | NMR sample preparation slides, including sample tube, solvent, and preparation considerations. |
| Common IconNMR Errors | PDF | `https://www.dropbox.com/s/ahbyq0qtcwf4xft/Common_Sample_Failures.pdf?dl=1` | Troubleshooting guide for IconNMR failures, including sample placement, bad shimming, air gaps, and sample quality problems. |
| Undergraduate Lab NMR training – J. Grimes | PDF | `https://www.dropbox.com/s/jy6493lc4p7omry/Bruker%20Undergraduate%20Automation%20Training%20_Current.pdf?dl=1` | Undergraduate teaching lab Bruker automation training. |

## NMR Application Notes

| Resource | Type | URL | Brief description |
| --- | --- | --- | --- |
| Solvent suppression | PDF | `https://www.dropbox.com/s/1tepqxxwlilu9n2/Solvent%20Suppression.pdf?dl=1` | NMR solvent suppression options and guidance for reducing large solvent or impurity resonances. |
| Diffusion spectroscopy | PDF | `https://www.dropbox.com/s/hfdddz8of4y18zh/DCIF%20-%20Diffusion%20Experiments%20rev1.pdf?dl=1` | Guide to NMR diffusion experiments using pulsed field gradients, with setup and processing notes. |
| T1 Measurement | PDF | `https://www.dropbox.com/s/owtxy7l7ch79c4e/T1_Measurement.pdf?dl=1` | Guide to NMR T1 measurement concepts and experimental setup. |
| Quantitative NMR | PDF | `https://www.dropbox.com/s/50tqj37i542viku/Quantitative_NMR_optimum_tip_angle.pdf?dl=1` | Quantitative NMR guidance, including tip angle and acquisition considerations. |
| Selective 1D experiments – general notes | PDF | `https://www.dropbox.com/s/9j4cxlcstl1a7zh/Selective%201D%20experiments.v2.pdf?dl=1` | General notes on selective 1D NMR experiments and when they are useful. |
| Selective 1D experiments on the Manual Bruker systems | PDF | `https://www.dropbox.com/s/5pa198ef7rifipv/Acquisition%20of%20Selective%201D%20Experiments.pdf?dl=1` | Practical acquisition guide for selective 1D experiments on manual Bruker systems. |
| STEP-NOESY (and ROESY) | PDF | `https://www.dropbox.com/s/yqv3mgg0x3p5thx/STEP_NOESY.pdf?dl=1` | Application note for STEP-NOESY and ROESY experiments. |
| Using Multizg for kinetics | PDF | `https://www.dropbox.com/s/349idl5htckcgf3/Using%20multizg.pdf?dl=1` | Notes on using MultiZG for repeated acquisitions and kinetics data. |
| Double-echo filtering | PDF | `https://chemistry.mit.edu/wp-content/uploads/2019/08/DCIF_Double_echo_filter.pdf` | Application note on double-echo filtering for selective NMR observation. |
| Introduction to 2D NMR | PDF | `https://www.dropbox.com/s/q3li1ll0d1gqgnj/2D_NMR_Introduction.pdf?dl=1` | Introductory guide to 2D NMR experiments and interpretation. |
| Small-molecule assignment sets | PDF | `https://www.dropbox.com/s/9ksetdyt8f2phdq/README.pdf?dl=1` | README-style support document associated with small-molecule assignment set resources. |
| Bruker VT guide | PDF | `https://www.dropbox.com/s/7rf2mftty57b9kq/Bruker501_VT_guide.pdf?dl=1` | Variable-temperature experiment guide for the Bruker 501, including temperature range and setup assumptions. |
| New experiment setup macros | PDF | `https://www.dropbox.com/s/tjqf38l95x6bho7/New%20experiment%20setup%20macros_external.pdf?dl=1` | Notes for using TopSpin macros to set up new NMR experiments. |

## Other Instrument Resources

| Resource | Type | URL | Brief description |
| --- | --- | --- | --- |
| EPR use | PDF | `https://www.dropbox.com/s/ec7nog7mjq5na9z/EPR_Overview_MIT.pdf?dl=1` | EPR hardware overview and training notes, including tuning and sample preparation considerations. |
| FTIR use | PDF | `https://www.dropbox.com/s/ppk7jgvoall43qb/FTIR%20Training%20Guide.pdf?dl=1` | FTIR training guide for Bruker Alpha II / ATR workflows. |
| JASCO Polarimeter use | PDF | `https://www.dropbox.com/s/xc2axmzy1t4k16e/Jasco-Polarimeter-Training.pdf?dl=1` | Polarimeter training guide for JASCO P-2000 operation and measurements. |
| Quick start guide – HPLC | PDF | `https://www.dropbox.com/s/snrdjm0sirj7ll6/HPLC_user%20guide.pdf?dl=1` | HPLC user guide for the analytical Agilent Infinity 1260 II system. |
| TDSpec Reference Manual | PDF | `https://www.dropbox.com/s/u3xlnpl2kxk1dq1/TDspecSoftware%20Manual.pdf?dl=1` | Time-domain NMR software reference manual, including experiment menus, data handling, and fitting. |
| Introduction to HPLC Separations – M. Kumar (2020-01-10) | PDF | `https://www.dropbox.com/s/c44lbd8u74wx9v5/Kumar_2020-01-10_chromatography.pdf?dl=1` | Seminar slides introducing HPLC separations and chromatography concepts. |

## Safety, Reservation, And Facility Support Resources

| Resource | Type | URL | Brief description |
| --- | --- | --- | --- |
| DCIF Safety Orientation | PDF | `https://www.dropbox.com/s/fdoj9hz28ryhaxe/DCIF_Safety_Orientation.pdf?dl=1` | DCIF-specific lab safety orientation and hazards, intended to supplement MIT EH&S practices. |
| Web-based reservations with Res1P | PDF | `https://www.dropbox.com/s/rk4drthl14pzc40/res1p_usage_v1.0.pdf?dl=1` | Res1P reservation system usage guide for instrument time reservations. |
| Data processing options | PDF | `https://chemistry.mit.edu/wp-content/uploads/2019/08/DCIF_under_construction.pdf` | Placeholder page indicating the DCIF data-processing content was under construction. |

## Seminar And Lecture Resources

| Resource | Type | URL | Brief description |
| --- | --- | --- | --- |
| Recent seminars | PDF | `https://www.dropbox.com/scl/fi/7fwzpx9qcruxxoq379ww6/DCIF-Seminar-Bruce-IAP-2024.pdf?rlkey=w1r6bkvmzqtk176onbt4a0sjw&dl=1` | Recent DCIF seminar slide deck. |
| NMR in Shared Labs in the COVID-19 Era – W. Massefski, NewNMR (2020-09-16) | PDF | `https://www.dropbox.com/s/f86eckbjlsaywmm/NewNMR_slides_2020-09-16.pdf?dl=1` | Seminar slides on operating NMR shared labs during COVID-era constraints. |
| 5.363 NMR lecture – W. Massefski | PDF | `https://www.dropbox.com/s/h5v1pzkhi2rq34h/5.363_Undergraduate_NMR_lecture_v3.pdf?dl=1` | Undergraduate NMR lecture slides covering core NMR concepts and workflows. |
| Undergraduate Lab (5.310) NMR Lecture – S. Willis | PDF | `https://www.dropbox.com/scl/fi/bjnpxhkeugpd0fvsiq8jm/NMR_lecture_092525.pdf?rlkey=o0q54op5nm876gs2c9bmw9gwb&dl=1` | Undergraduate laboratory NMR lecture slides by Sarah Willis. |
| Undergraduate Lab NMR lecture – J. Grimes | PDF | `https://www.dropbox.com/s/jy6493lc4p7omry/Bruker%20Undergraduate%20Automation%20Training%20_Current.pdf?dl=1` | Undergraduate NMR lecture/training material using the Bruker automation training document. |
| Product Operators in NMR – B. Adams (2020-01) | PDF | `https://www.dropbox.com/s/qzuv4jbh606pp1p/Adams_2020-01_prodop_course.pdf?dl=1` | Advanced NMR seminar/course material on product operators. |

## Overview-Listed Resources Without Separate Crawled PDF Snapshots

These entries appear as structured guide/resource records from the overview page. They may be page
text, non-PDF links, or resources represented indirectly by one of the crawled PDFs above.

| Overview resource record | Category | Where represented | Brief description |
| --- | --- | --- | --- |
| Below are a series of application notes that describe special applications or the use of DCIF instruments in the study of non-standard samples. | Application Notes | Overview page | Introductory overview text for the application-notes section. |
| Neo402 Batch Automation spreadsheet | Batch NMR automation | Overview page | Batch automation spreadsheet link for the Neo402 spectrometer. |
| Avance400 Batch Automation spreadsheet | Batch NMR automation | Overview page | Batch automation spreadsheet link for the Avance400 spectrometer. |
| Neo500 Batch Automation spreadsheet | Batch NMR automation | Overview page | Batch automation spreadsheet link for the Neo500 spectrometer. |
| Neo600 Batch Automation spreadsheet | Batch NMR automation | Overview page | Batch automation spreadsheet link for the Neo600 spectrometer. |
| Be sure to use the correct spreadsheet; different spectrometers have different capabilities. | Batch NMR automation | Overview page | Cautionary note attached to the batch automation spreadsheet list. |
| The DCIF sponsors seminars through our own Seminar series (including occasional external seminars), gives guest lectures as part of the MIT Chemistry curriculum, and runs informal short courses on advanced topics in spectroscopy. Slides from some of these presentations can be found below. | DCIF Seminar series | Overview page | Introductory overview text for seminar and course materials. |
| Bruce also gave a summary of this mini course as a NewNMR Seminar; the slides for this seminar can be found here – Shaped Pulses – Application and Practice, NewNMR (2023-07-24) (notes on the slides are available here ). | DCIF Seminar series | Overview page | Overview-listed shaped-pulses seminar and notes resource. |

## Notes For Maintainers

- The exact crawled source list is defined by `data/raw/*.meta.json`.
- Parsed page/section text is in `data/normalized/*.json`.
- Structured inventories, fee rows, staff rows, and guide link records are in
  `data/structured/records.jsonl`.
- Retrieval chunks are in `data/chunks/chunks.jsonl`.
- If this catalog becomes stale, rerun the ingest pipeline and compare this document against the
  regenerated metadata and structured records.
