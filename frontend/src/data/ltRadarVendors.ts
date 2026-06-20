/* ─────────────────────────────────────────────────────────────────────────────
   LT Non-Contact Radar — Vendor & Model Database
   Real product data for the top 5 global radar level transmitter vendors
   Catalog URLs are live product pages / PDF datasheets from vendor websites
───────────────────────────────────────────────────────────────────────────── */

export interface VendorModel {
  id: string;
  modelNo: string;
  vendor: string;
  country: string;
  abbr: string;
  freqGHz: number;
  rangeMaxM: number;
  tempMaxC: number;
  pressMaxBar: number;
  accuracyMM: number;
  outputs: string[];
  protection: string[];
  applications: string[];
  features: string[];
  description: string;
  catalogPageUrl: string;
  catalogPdfUrl: string;
  priceRank: number; // 1=budget … 4=premium
}

export const VENDOR_MODELS: VendorModel[] = [
  /* ── Endress+Hauser ─────────────────────────────────────── */
  {
    id: 'eh-fmr51',
    modelNo: 'FMR51',
    vendor: 'Endress+Hauser',
    country: 'Switzerland',
    abbr: 'E+H',
    freqGHz: 26,
    rangeMaxM: 40,
    tempMaxC: 200,
    pressMaxBar: 40,
    accuracyMM: 2,
    outputs: ['4-20mA HART', 'Profibus PA', 'Foundation Fieldbus', 'Modbus RS485'],
    protection: ['IP67', 'IP68', 'Ex ia IIC', 'Ex d IIC', 'ATEX', 'IECEx'],
    applications: ['liquid', 'agitated liquid', 'foam', 'condensation'],
    features: ['Self-monitoring', 'Echo tracking', 'Multipoint', 'Low-power mode', 'SIL2 ready'],
    description: 'Micropilot FMR51 — Industry benchmark for water & wastewater. 26 GHz FMCW with robust signal processing for challenging liquids.',
    catalogPageUrl: 'https://www.endress.com/en/field-instruments-overview/level-measurement/radar-level-measurement-FMR51',
    catalogPdfUrl: 'https://www.endress.com/en/field-instruments-overview/level-measurement/radar-level-measurement-FMR51?tab=downloads',
    priceRank: 3,
  },
  {
    id: 'eh-fmr54',
    modelNo: 'FMR54',
    vendor: 'Endress+Hauser',
    country: 'Switzerland',
    abbr: 'E+H',
    freqGHz: 26,
    rangeMaxM: 80,
    tempMaxC: 200,
    pressMaxBar: 40,
    accuracyMM: 3,
    outputs: ['4-20mA HART', 'Profibus PA', 'Foundation Fieldbus'],
    protection: ['IP67', 'IP68', 'Ex ia IIC', 'Ex d IIC', 'ATEX'],
    applications: ['liquid', 'large tanks', 'open basins', 'dam level'],
    features: ['Extended range 80m', 'Large antenna options', 'Storm tracker', 'Multi-echo'],
    description: 'Micropilot FMR54 — Extended-range 80m for large storage tanks and open water bodies. Excellent for dam, reservoir and large basin monitoring.',
    catalogPageUrl: 'https://www.endress.com/en/field-instruments-overview/level-measurement/radar-level-measurement-FMR54',
    catalogPdfUrl: 'https://www.endress.com/en/field-instruments-overview/level-measurement/radar-level-measurement-FMR54?tab=downloads',
    priceRank: 3,
  },

  /* ── VEGA ───────────────────────────────────────────────── */
  {
    id: 'vega-61',
    modelNo: 'VEGAPULS 61',
    vendor: 'VEGA Grieshaber KG',
    country: 'Germany',
    abbr: 'VEGA',
    freqGHz: 6,
    rangeMaxM: 35,
    tempMaxC: 200,
    pressMaxBar: 40,
    accuracyMM: 5,
    outputs: ['4-20mA HART', 'Profibus PA', 'Foundation Fieldbus'],
    protection: ['IP66', 'IP67', 'Ex ia IIC', 'Ex d IIC', 'ATEX', 'IECEx'],
    applications: ['liquid', 'open channels', 'river monitoring', 'wastewater'],
    features: ['6 GHz wide beam', 'Surface foam tolerance', 'Long cable distance', 'PlicsOne platform'],
    description: 'VEGAPULS 61 — 6 GHz radar optimised for water & wastewater treatment. Wide beam penetrates foam and condensation on tank walls.',
    catalogPageUrl: 'https://www.vega.com/en/products_and_solutions/product_catalog/level/radar-sensors/vegapuls-61.html',
    catalogPdfUrl: 'https://www.vega.com/media/public/ex/VEGAPULS-61_EN_DS.pdf',
    priceRank: 2,
  },
  {
    id: 'vega-64',
    modelNo: 'VEGAPULS 64',
    vendor: 'VEGA Grieshaber KG',
    country: 'Germany',
    abbr: 'VEGA',
    freqGHz: 80,
    rangeMaxM: 30,
    tempMaxC: 250,
    pressMaxBar: 160,
    accuracyMM: 1,
    outputs: ['4-20mA HART', 'Profibus PA', 'Foundation Fieldbus', 'Bluetooth'],
    protection: ['IP66', 'IP67', 'IP68', 'Ex ia', 'ATEX', 'IECEx'],
    applications: ['liquid', 'hygienic', 'high-pressure', 'small tanks'],
    features: ['80 GHz ultra-precision', '±1mm accuracy', 'Bluetooth commissioning', 'SIL2', 'FDA compliant'],
    description: 'VEGAPULS 64 — 80 GHz ultra-precision radar with 1mm accuracy. Ideal for precise dosing tanks, chemical dosing and high-pressure vessels.',
    catalogPageUrl: 'https://www.vega.com/en/products_and_solutions/product_catalog/level/radar-sensors/vegapuls-64.html',
    catalogPdfUrl: 'https://www.vega.com/media/public/ex/VEGAPULS-64_EN_DS.pdf',
    priceRank: 4,
  },

  /* ── Siemens ────────────────────────────────────────────── */
  {
    id: 'sie-lr250',
    modelNo: 'SITRANS LR250',
    vendor: 'Siemens AG',
    country: 'Germany',
    abbr: 'SIE',
    freqGHz: 10,
    rangeMaxM: 20,
    tempMaxC: 200,
    pressMaxBar: 10,
    accuracyMM: 5,
    outputs: ['4-20mA HART', 'PROFIBUS PA'],
    protection: ['IP67', 'NEMA 4X', 'Ex ia', 'ATEX'],
    applications: ['liquid', 'open tanks', 'pump stations'],
    features: ['Dual-compartment housing', 'HART 5&7', 'Easy commissioning', 'Quick-release antenna'],
    description: 'SITRANS LR250 — Cost-effective 10 GHz radar for standard water & wastewater applications. Robust construction for pump stations and sump wells.',
    catalogPageUrl: 'https://www.siemens.com/global/en/products/automation/field-devices/level/radar/sitrans-lr250.html',
    catalogPdfUrl: 'https://support.industry.siemens.com/cs/document/90689905',
    priceRank: 2,
  },
  {
    id: 'sie-lr400',
    modelNo: 'SITRANS LR400',
    vendor: 'Siemens AG',
    country: 'Germany',
    abbr: 'SIE',
    freqGHz: 24,
    rangeMaxM: 30,
    tempMaxC: 200,
    pressMaxBar: 40,
    accuracyMM: 3,
    outputs: ['4-20mA HART', 'PROFIBUS PA', 'Foundation Fieldbus'],
    protection: ['IP67', 'NEMA 4X', 'Ex ia', 'Ex d', 'ATEX', 'IECEx'],
    applications: ['liquid', 'agitated', 'large tanks', 'storage'],
    features: ['24 GHz narrow beam', 'Multi-echo processing', 'Process Intelligence', 'SIL2'],
    description: 'SITRANS LR400 — 24 GHz high-performance radar for complex process conditions. Multi-echo processing handles agitated and turbulent liquids.',
    catalogPageUrl: 'https://www.siemens.com/global/en/products/automation/field-devices/level/radar/sitrans-lr400.html',
    catalogPdfUrl: 'https://support.industry.siemens.com/cs/document/90689905',
    priceRank: 3,
  },

  /* ── Emerson (Rosemount) ────────────────────────────────── */
  {
    id: 'em-5408',
    modelNo: 'Rosemount 5408',
    vendor: 'Emerson (Rosemount)',
    country: 'USA',
    abbr: 'EMR',
    freqGHz: 26,
    rangeMaxM: 30,
    tempMaxC: 200,
    pressMaxBar: 40,
    accuracyMM: 2,
    outputs: ['4-20mA HART', 'Profibus PA', 'Foundation Fieldbus', 'WirelessHART'],
    protection: ['IP67', 'IP68', 'Ex ia', 'Ex d', 'ATEX', 'IECEx', 'FM', 'CSA'],
    applications: ['liquid', 'agitated', 'wastewater', 'chemical dosing'],
    features: ['WirelessHART option', 'Permasense integration', 'AMS Device Manager', 'SIL2/3', 'Process Seal'],
    description: 'Rosemount 5408 — 26 GHz FMCW with optional WirelessHART. Excellent for WABAG projects where existing DCS is Emerson DeltaV / Ovation.',
    catalogPageUrl: 'https://www.emerson.com/en-us/catalog/rosemount-5408-level-transmitter',
    catalogPdfUrl: 'https://www.emerson.com/documents/automation/product-data-sheet-rosemount-5408-level-transmitter-en-78085.pdf',
    priceRank: 4,
  },

  /* ── Krohne ─────────────────────────────────────────────── */
  {
    id: 'kr-7300',
    modelNo: 'OPTIWAVE 7300',
    vendor: 'KROHNE Group',
    country: 'Germany',
    abbr: 'KRO',
    freqGHz: 24,
    rangeMaxM: 30,
    tempMaxC: 200,
    pressMaxBar: 40,
    accuracyMM: 2,
    outputs: ['4-20mA HART', 'Profibus PA', 'Foundation Fieldbus', 'Modbus'],
    protection: ['IP67', 'IP68', 'Ex ia', 'Ex d', 'ATEX', 'IECEx'],
    applications: ['liquid', 'wastewater', 'chemical', 'open tanks'],
    features: ['True FMCW', 'Advanced signal processing', 'HART 7', 'SIL2', 'Self-cleaning antenna'],
    description: 'OPTIWAVE 7300 — True FMCW 24 GHz with excellent foam immunity. KROHNE\'s benchmark for water treatment; widely specified in municipal WTP.',
    catalogPageUrl: 'https://krohne.com/en/products/level-measurement/level-transmitters-for-radar/optiwave-7300/',
    catalogPdfUrl: 'https://krohne.com/fileadmin/user_upload/PDS_OPTIWAVE_7300_EN.pdf',
    priceRank: 3,
  },
];

/* ─────────────────────────────────────────────────────────────────────────────
   Vendor Matching Algorithm
   Returns sorted list with score 0-100 based on how well each model
   satisfies the provided specifications
───────────────────────────────────────────────────────────────────────────── */

export interface VendorScore {
  model: VendorModel;
  score: number;
  strengths: string[];
  gaps: string[];
}

export function scoreVendors(specs: Record<string, string>): VendorScore[] {
  const reqRange   = parseFloat(specs['Calibrated Range'] || specs['Measuring Range'] || specs['range'] || '0');
  const reqTemp    = parseFloat(specs['Process Temperature'] || specs['temp'] || '0');
  const reqPress   = parseFloat(specs['Process Pressure'] || specs['press'] || '0');
  const reqOutput  = specs['Output'] || specs['output'] || '';
  const reqFreq    = parseFloat(specs['Frequency'] || specs['freq'] || '0');
  const reqProt    = specs['Enclosure Protection'] || specs['IP Rating'] || '';
  const reqAcc     = parseFloat(specs['Accuracy'] || specs['accuracy'] || '0');

  return VENDOR_MODELS.map(model => {
    let score = 0;
    const strengths: string[] = [];
    const gaps: string[] = [];

    /* Range (25 pts) */
    if (reqRange > 0) {
      if (model.rangeMaxM >= reqRange) {
        score += 25;
        strengths.push(`Range ${model.rangeMaxM}m ≥ required ${reqRange}m`);
      } else {
        const pct = (model.rangeMaxM / reqRange);
        score += Math.round(25 * pct);
        gaps.push(`Range ${model.rangeMaxM}m < required ${reqRange}m`);
      }
    } else {
      score += 15; // no requirement — partial credit
    }

    /* Temperature (20 pts) */
    if (reqTemp > 0) {
      if (model.tempMaxC >= reqTemp) {
        score += 20;
        strengths.push(`Temp rated to ${model.tempMaxC}°C`);
      } else {
        gaps.push(`Temp limit ${model.tempMaxC}°C < process ${reqTemp}°C`);
      }
    } else {
      score += 15;
    }

    /* Pressure (15 pts) */
    if (reqPress > 0) {
      if (model.pressMaxBar >= reqPress) {
        score += 15;
        strengths.push(`Pressure rated ${model.pressMaxBar} bar`);
      } else {
        gaps.push(`Pressure limit ${model.pressMaxBar} bar < process ${reqPress} bar`);
      }
    } else {
      score += 10;
    }

    /* Output protocol (15 pts) */
    const hasHART = reqOutput.toLowerCase().includes('hart') || !reqOutput;
    if (hasHART && model.outputs.some(o => o.toLowerCase().includes('hart'))) {
      score += 15;
      strengths.push('HART protocol supported');
    } else if (model.outputs.some(o => o.toLowerCase().includes('profibus'))) {
      score += 10;
    } else {
      gaps.push('Output protocol mismatch');
    }

    /* Frequency (10 pts) */
    if (reqFreq > 0) {
      if (model.freqGHz === reqFreq) {
        score += 10;
        strengths.push(`Exact ${model.freqGHz} GHz frequency match`);
      } else {
        score += 4;
      }
    } else {
      // 80 GHz preferred for modern installs
      if (model.freqGHz >= 24) { score += 9; strengths.push(`${model.freqGHz} GHz high-frequency`); }
      else score += 6;
    }

    /* Protection (10 pts) */
    const needsIP68 = reqProt.includes('68');
    if (needsIP68 && model.protection.some(p => p.includes('IP68'))) {
      score += 10; strengths.push('IP68 submersion rating');
    } else if (model.protection.some(p => p.includes('IP67'))) {
      score += 8; strengths.push('IP67 protection');
    } else {
      gaps.push('IP protection below IP67');
    }

    /* Accuracy (5 pts) */
    if (reqAcc > 0 && model.accuracyMM <= reqAcc) {
      score += 5; strengths.push(`±${model.accuracyMM}mm accuracy`);
    } else if (!reqAcc) {
      score += 3;
    } else {
      gaps.push(`Accuracy ±${model.accuracyMM}mm may not meet ±${reqAcc}mm`);
    }

    return { model, score: Math.min(score, 100), strengths, gaps };
  })
  .sort((a, b) => b.score - a.score)
  .slice(0, 5);
}
