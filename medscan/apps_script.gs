// ═══════════════════════════════════════════════════════════════
//  MedScan — Google Apps Script
//  Paste this entire file into your Google Sheet's Apps Script editor
//  Extensions → Apps Script → paste → Save → Deploy
// ═══════════════════════════════════════════════════════════════

const SHEET_NAME = "MedScan";

const COLUMNS = [
  "Timestamp", "Patient Name", "Age", "Gender",
  "Height (cm)", "Weight (kg)", "BMI",
  "Systolic BP", "Diastolic BP", "BP Status",
  "Fasting Sugar (mg/dL)", "Post Prandial Sugar (mg/dL)", "Sugar Status"
];

// ── Initialise sheet with header row if needed ──────────────────
function getOrCreateSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let ws = ss.getSheetByName(SHEET_NAME);

  if (!ws) {
    ws = ss.insertSheet(SHEET_NAME);

    // Write header row
    ws.appendRow(COLUMNS);

    // Style the header
    const headerRange = ws.getRange(1, 1, 1, COLUMNS.length);
    headerRange.setBackground("#1F4E79");
    headerRange.setFontColor("#FFFFFF");
    headerRange.setFontWeight("bold");
    headerRange.setHorizontalAlignment("center");
    headerRange.setFontSize(11);

    // Freeze header row
    ws.setFrozenRows(1);

    // Set column widths
    const widths = [140, 180, 50, 70, 90, 90, 60, 90, 95, 100, 150, 180, 220];
    widths.forEach((w, i) => ws.setColumnWidth(i + 1, w));
  }
  return ws;
}

// ── Handle POST — append rows ───────────────────────────────────
function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);

    if (payload.action === "append") {
      const ws   = getOrCreateSheet();
      const rows = payload.rows || [];

      rows.forEach(row => {
        const rowData = COLUMNS.map(col => row[col] || "");
        ws.appendRow(rowData);

        // Colour-code BP Status cell
        const lastRow  = ws.getLastRow();
        const bpColIdx = COLUMNS.indexOf("BP Status") + 1;
        const bpCell   = ws.getRange(lastRow, bpColIdx);
        const bpVal    = row["BP Status"] || "";

        if (bpVal === "High") {
          bpCell.setBackground("#FFD7D7").setFontColor("#C00000").setFontWeight("bold");
        } else if (bpVal === "Elevated") {
          bpCell.setBackground("#FFF2CC").setFontColor("#7F6000").setFontWeight("bold");
        } else if (bpVal === "Normal") {
          bpCell.setBackground("#E2EFDA").setFontColor("#375623").setFontWeight("bold");
        }

        // Colour-code Sugar Status cell
        const sgColIdx = COLUMNS.indexOf("Sugar Status") + 1;
        const sgCell   = ws.getRange(lastRow, sgColIdx);
        const sgVal    = row["Sugar Status"] || "";

        if (sgVal.includes("Diabetic") && !sgVal.includes("Pre")) {
          sgCell.setBackground("#FFD7D7").setFontColor("#C00000").setFontWeight("bold");
        } else if (sgVal.includes("Pre")) {
          sgCell.setBackground("#FFF2CC").setFontColor("#7F6000").setFontWeight("bold");
        } else if (sgVal.includes("Normal")) {
          sgCell.setBackground("#E2EFDA").setFontColor("#375623").setFontWeight("bold");
        }

        // Alternate row shading
        if (lastRow % 2 === 0) {
          ws.getRange(lastRow, 1, 1, COLUMNS.length).setBackground("#EBF3FB");
        }
      });

      return jsonResponse({ status: "ok", saved: rows.length, total: ws.getLastRow() - 1 });
    }

    return jsonResponse({ status: "error", message: "Unknown action" });

  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// ── Handle GET — read all rows ──────────────────────────────────
function doGet(e) {
  try {
    const action = e.parameter.action;

    if (action === "read") {
      const ws     = getOrCreateSheet();
      const values = ws.getDataRange().getValues();

      if (values.length <= 1) {
        return jsonResponse({ status: "ok", data: [] });
      }

      const headers = values[0];
      const data    = values.slice(1).map(row => {
        const obj = {};
        headers.forEach((h, i) => obj[h] = row[i] || "");
        return obj;
      });

      return jsonResponse({ status: "ok", data: data });
    }

    return jsonResponse({ status: "error", message: "Unknown action" });

  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// ── Helper ──────────────────────────────────────────────────────
function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
