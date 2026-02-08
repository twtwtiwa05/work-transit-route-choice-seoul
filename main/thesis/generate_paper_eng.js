const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, BorderStyle, WidthType,
        PageNumber, LevelFormat, ShadingType, VerticalAlign, ImageRun } = require('docx');
const fs = require('fs');

// Load images with existence check
const figuresDir = "/Users/kimtaewoo/Documents/연구/main_project/최적경로 일치여부/probabilistic-otp/docs/figures/";
const figureFiles = [
    "figure1_research_framework.png",
    "figure2_jaccard_distribution.png",
    "figure3_parameter_comparison.png"
];
for (const f of figureFiles) {
    if (!fs.existsSync(figuresDir + f)) {
        console.error(`ERROR: ${f} not found in ${figuresDir}`);
        process.exit(1);
    }
}
const figure1Data = fs.readFileSync(figuresDir + "figure1_research_framework.png");
const figure2Data = fs.readFileSync(figuresDir + "figure2_jaccard_distribution.png");
const figure3Data = fs.readFileSync(figuresDir + "figure3_parameter_comparison.png");

// A4 size: 210 x 297mm, 25mm margins (1 inch = 1440 twips)
const MARGIN = 1440;

// Table border style
const tableBorder = { style: BorderStyle.SINGLE, size: 1, color: "000000" };
const cellBorders = { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder };

// Helper functions - adjusted for template (11pt = 22 half-points)
function createCell(text, bold = false, width = null, align = AlignmentType.LEFT, shading = null) {
    const cellOptions = {
        borders: cellBorders,
        verticalAlign: VerticalAlign.CENTER,
        children: [new Paragraph({
            alignment: align,
            children: [new TextRun({ text: text, bold: bold, size: 22, font: "Times New Roman" })]
        })]
    };
    if (width) cellOptions.width = { size: width, type: WidthType.DXA };
    if (shading) cellOptions.shading = { fill: shading, type: ShadingType.CLEAR };
    return new TableCell(cellOptions);
}

function createHeaderRow(texts, widths) {
    return new TableRow({
        tableHeader: true,
        children: texts.map((text, i) => createCell(text, true, widths[i], AlignmentType.CENTER, "D9D9D9"))
    });
}

function createDataRow(texts, widths, aligns = null) {
    return new TableRow({
        children: texts.map((text, i) => createCell(text, false, widths[i], aligns ? aligns[i] : AlignmentType.LEFT))
    });
}

function createFigure(imageData, caption, width = 500, height = 350) {
    return [
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 240, after: 120 },
            children: [new ImageRun({
                type: "png",
                data: imageData,
                transformation: { width: width, height: height }
            })]
        }),
        new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { after: 240 },
            children: [new TextRun({ text: caption, bold: true, size: 24, font: "Times New Roman" })]
        })
    ];
}

// Create the document following template specifications
const doc = new Document({
    styles: {
        default: {
            document: {
                run: { font: "Times New Roman", size: 24 }  // 12pt default
            }
        },
        paragraphStyles: [
            // Paper title: 18pt, bold, centered, capitals
            { id: "PaperTitle", name: "Paper Title", basedOn: "Normal",
              run: { size: 36, bold: true, font: "Times New Roman" },
              paragraph: { spacing: { before: 0, after: 240 }, alignment: AlignmentType.CENTER } },
            // First level heading: 16pt, bold, centered, all caps
            { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 32, bold: true, font: "Times New Roman", allCaps: true },
              paragraph: { spacing: { before: 360, after: 240 }, alignment: AlignmentType.CENTER } },
            // Second level heading: 14pt, bold, flush left, all caps
            { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 28, bold: true, font: "Times New Roman", allCaps: true },
              paragraph: { spacing: { before: 280, after: 200 }, alignment: AlignmentType.LEFT } },
            // Third level heading: 12pt, bold, flush left, initial caps
            { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 24, bold: true, font: "Times New Roman" },
              paragraph: { spacing: { before: 240, after: 160 }, alignment: AlignmentType.LEFT } },
            // Fourth level heading: 12pt, bold, italic, flush left
            { id: "Heading4", name: "Heading 4", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 24, bold: true, italics: true, font: "Times New Roman" },
              paragraph: { spacing: { before: 200, after: 120 }, alignment: AlignmentType.LEFT } },
            // Normal: 12pt, justified, single spacing, 0pt spacing (per template)
            { id: "Normal", name: "Normal",
              run: { size: 24, font: "Times New Roman" },
              paragraph: { spacing: { before: 0, after: 0, line: 240, lineRule: "auto" }, alignment: AlignmentType.JUSTIFIED } },
            // Table caption: 12pt, bold (below table per template, 0pt before, space after)
            { id: "TableCaption", name: "Table Caption", basedOn: "Normal",
              run: { size: 24, bold: true, font: "Times New Roman" },
              paragraph: { spacing: { before: 60, after: 240 }, alignment: AlignmentType.LEFT } },
            // Author info: 12pt, bold, centered
            { id: "Author", name: "Author", basedOn: "Normal",
              run: { size: 24, bold: true, font: "Times New Roman" },
              paragraph: { spacing: { after: 60 }, alignment: AlignmentType.CENTER } }
        ]
    },
    numbering: {
        config: [
            { reference: "ref-list",
              levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "(%1)", alignment: AlignmentType.LEFT,
                style: { paragraph: { indent: { left: 360, hanging: 360 } } } }] }
        ]
    },
    sections: [{
        properties: {
            page: {
                margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
                size: { width: 11906, height: 16838 }  // A4
            }
        },
        footers: {
            default: new Footer({
                children: [new Paragraph({
                    alignment: AlignmentType.CENTER,
                    children: [new TextRun({ children: [PageNumber.CURRENT], font: "Times New Roman", size: 24 })]
                })]
            })
        },
        children: [
            // ========== TITLE (18pt, centered, capitals) ==========
            new Paragraph({
                style: "PaperTitle",
                children: [new TextRun({
                    text: "DO TRANSIT USERS MAXIMIZE UTILITY OR FOLLOW ALGORITHMS?",
                    bold: true, size: 36, font: "Times New Roman"
                })]
            }),
            new Paragraph({
                style: "PaperTitle",
                children: [new TextRun({
                    text: "DEVELOPING USER-TYPE-SPECIFIC PROBABILISTIC ROUTE ASSIGNMENT",
                    bold: true, size: 36, font: "Times New Roman"
                })]
            }),

            // ========== AUTHORS (12pt bold) ==========
            // Gachon University authors (grouped)
            new Paragraph({
                style: "Author",
                spacing: { before: 360, after: 60 },
                children: [new TextRun({ text: "Tae Woo Kim*, Minsu Kim, Jiho Yeo", bold: true, size: 24, font: "Times New Roman" })]
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 60 },
                children: [new TextRun({ text: "Department of Smart City, Gachon University", size: 24, font: "Times New Roman" })]
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 60 },
                children: [new TextRun({ text: "1342 Seongnam-daero, Sujeong-gu, Seongnam-si, Gyeonggi-do, Republic of Korea", size: 24, font: "Times New Roman" })]
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 120 },
                children: [new TextRun({ text: "TEL: [Phone], E-mail: [Email]", size: 24, font: "Times New Roman" })]
            }),

            // Sung-taek Choi (Hanyang University)
            new Paragraph({
                style: "Author",
                spacing: { before: 120, after: 60 },
                children: [new TextRun({ text: "Sung-taek Choi", bold: true, size: 24, font: "Times New Roman" })]
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 60 },
                children: [new TextRun({ text: "Department of Urban Engineering, Hanyang University", size: 24, font: "Times New Roman" })]
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 360 },
                children: [new TextRun({ text: "Seoul, Republic of Korea", size: 24, font: "Times New Roman" })]
            }),

            // ========== ABSTRACT (250 words, SCI-quality) ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "ABSTRACT", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Transit route choice models have conventionally assumed homogeneous preferences, overlooking behavioral differences among user types. Using 187,010 trips from Seoul's smart card data, we estimate user-type-specific route choice parameters with Multinomial Logit (MNL) models. Elderly users exhibit 47% stronger transfer aversion and 90% stronger subway preference compared to general users. Walking time is perceived as 8.5 times more burdensome than in-vehicle time—substantially higher than the 2–3× typically assumed in routing algorithms. We developed a probabilistic route assignment module integrated with OpenTripPlanner (OTP) for user-type-specific route recommendations. Hold-out validation confirmed robust model performance with no evidence of overfitting. While 38% of trips achieve exact route matching with OTP alternatives, 28% show higher similarity with non-optimal-cost routes, suggesting route choice factors beyond generalized cost. The framework connects route choice theory with practical routing systems and provides empirical grounding for personalized transit services.",
                    size: 24, font: "Times New Roman"
                })]
            }),
            new Paragraph({
                style: "Normal",
                spacing: { before: 120, after: 360 },
                children: [
                    new TextRun({ text: "Keywords: ", bold: true, size: 24, font: "Times New Roman" }),
                    new TextRun({ text: "Transit route choice, Multinomial Logit, Smart card big data, User heterogeneity, Probabilistic route assignment, OpenTripPlanner", size: 24, font: "Times New Roman" })
                ]
            }),

            // ========== 1. INTRODUCTION ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "INTRODUCTION", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "BACKGROUND", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Transit routing systems have become essential infrastructure for modern urban transportation. Commercial services such as Google Maps, Naver Maps, and Kakao Maps, along with open-source platforms like OpenTripPlanner (OTP), perform millions of route recommendations daily. These systems universally adopt deterministic routing approaches, presenting a single \"optimal\" route that minimizes a predefined generalized cost for any given origin-destination (OD) pair.",
                    size: 24, font: "Times New Roman"
                })]
            }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "However, actual transit user behavior is more complex. Different users select different routes for identical OD pairs, and even the same user may choose differently depending on circumstances. Behavioral variations by user type are policy-relevant, as the elderly, disabled, and children may exhibit route choice patterns distinct from general users. Routing systems that ignore these differences will diverge from actual travel behavior.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "RESEARCH GAPS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Existing research has three limitations. First, data scale: traditional route choice studies rely on surveys or GPS tracking with hundreds to thousands of observations, insufficient for estimating segment-specific parameters. Second, user heterogeneity: most studies assume a single user group or distinguish only two groups (e.g., commuters vs. non-commuters), ignoring demographic heterogeneity. Third, implementation gap: route choice model research typically concludes at parameter estimation without integration into operational routing systems.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "RESEARCH OBJECTIVES", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "This study establishes three objectives to overcome these limitations: (1) Large-scale MNL model estimation using smart card big data: estimate route choice parameters using 187,010 trips from Seoul. (2) Quantification of behavioral heterogeneity by user type: estimate separate models for five user types—general, elderly, disabled, youth, and children—and statistically test inter-type behavioral differences. (3) Development of probabilistic route assignment system: develop a probabilistic route assignment module integrated with OTP that enables user-type-specific route recommendations.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // ========== 2. LITERATURE REVIEW ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "LITERATURE REVIEW", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "TRANSIT ROUTE CHOICE MODELS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Route choice models are grounded in random utility theory (2), where users select routes that maximize utility among available alternatives. A comprehensive review (10) identified three core methodological issues: alternative route set generation, route attribute definition, and model structure selection. Smart card data address the first issue by revealing actual chosen routes, though the unchosen alternative set must still be inferred.",
                    size: 24, font: "Times New Roman"
                })]
            }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "The emergence of smart card data has enabled large-scale empirical research. A Seoul study (9) used transit card data to estimate route choice models, achieving 67% route recovery rate. Another study (1) developed an experiential learning-based route choice model using smart card data from Santiago, Chile.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "TRANSFER PENALTY RESEARCH", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Transfers constitute a critical disutility factor in transit route choice. An international study (8) analyzed data from five countries, reporting pure transfer penalties of 13–18 minutes. For Seoul, a prior study (14) estimated an average transfer penalty of 11.24 minutes using transit card data but did not disaggregate by user type. Whether transfer aversion varies systematically across demographic groups remains an open empirical question.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "USER HETEROGENEITY RESEARCH", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Behavioral differences in route choice by user characteristics have received growing attention. One study (4) documented preference heterogeneity in elderly bus accessibility evaluation in China, while another (13) found that elderly travelers are 10.2 percentage points less likely to use express trains compared to general users. These studies examine single user groups in isolation; to date, no study has simultaneously compared route choice behavior across multiple demographic segments including elderly, disabled, youth, and children within a unified framework.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "DIFFERENTIATION FROM PRIOR RESEARCH", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({ text: "Table 1 summarizes the differences between this study and major prior research.", size: 24, font: "Times New Roman" })]
            }),

            // Table 1: Comparison with Prior Studies
            new Table({
                columnWidths: [1500, 1500, 1500, 1800, 1800],
                rows: [
                    createHeaderRow(["Criterion", "(9)", "(14)", "(1)", "This Study"], [1500, 1500, 1500, 1800, 1800]),
                    createDataRow(["Data Scale", "~10,000s", "~1,000s", "~100,000", "187,010"], [1500, 1500, 1500, 1800, 1800]),
                    createDataRow(["User Types", "Single", "Single", "Single", "5 Types"], [1500, 1500, 1500, 1800, 1800]),
                    createDataRow(["Subway Pref.", "×", "×", "×", "○"], [1500, 1500, 1500, 1800, 1800]),
                    createDataRow(["Heterogeneity", "×", "×", "×", "○ (Quantified)"], [1500, 1500, 1500, 1800, 1800]),
                    createDataRow(["System Integ.", "×", "×", "×", "○ (OTP)"], [1500, 1500, 1500, 1800, 1800]),
                    createDataRow(["Hold-out Val.", "×", "×", "×", "○"], [1500, 1500, 1500, 1800, 1800])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 1. Comparison with Prior Research", bold: true })] }),

            // ========== 3. DATA AND METHODOLOGY ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "DATA AND METHODOLOGY", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "DATA OVERVIEW", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "This study utilizes Seoul's smart card big data. The analysis date is November 14, 2024 (Thursday), representing typical weekday travel patterns. The original dataset comprises 886,769 trips, from which 337,605 trips with exact OTP route matching (Jaccard = 1.0) were extracted. After removing duplicate routes, the final analysis sample consists of 187,010 trips.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // Table 2: User Type Distribution
            new Table({
                columnWidths: [2000, 1500, 2500, 1500],
                rows: [
                    createHeaderRow(["User Type", "Code", "Trips", "Share"], [2000, 1500, 2500, 1500]),
                    createDataRow(["General", "01", "154,897", "82.8%"], [2000, 1500, 2500, 1500]),
                    createDataRow(["Elderly", "04", "16,080", "8.6%"], [2000, 1500, 2500, 1500]),
                    createDataRow(["Youth", "03", "8,329", "4.5%"], [2000, 1500, 2500, 1500]),
                    createDataRow(["Disabled", "05", "5,823", "3.1%"], [2000, 1500, 2500, 1500]),
                    createDataRow(["Children", "02", "1,881", "1.0%"], [2000, 1500, 2500, 1500]),
                    createDataRow(["Total", "-", "187,010", "100%"], [2000, 1500, 2500, 1500])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 2. User Type Distribution", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "ROUTE GENERATION AND MATCHING", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Korean OTP, developed by our research team, is a RAPTOR (Round-based Public Transit Routing Algorithm)-based routing engine. It generates up to 5 multi-criteria Pareto-optimal routes for each OD pair. Jaccard similarity was used to match smart card trips with OTP alternative routes, with only exact matches (Jaccard = 1.0) included in the analysis.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "ROUTE SIMILARITY ANALYSIS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Prior to MNL model estimation, we analyzed similarity between actual smart card routes and OTP recommended routes to validate the quality of the OTP alternative route set (choice set) and the predictive power of the routing algorithm. Table 3 presents definitions of five similarity metrics.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // Table 3: Similarity Metrics Definition
            new Table({
                columnWidths: [2000, 3500, 1000, 2500],
                rows: [
                    createHeaderRow(["Metric", "Definition", "Range", "Description"], [2000, 3500, 1000, 2500]),
                    createDataRow(["Modal Match", "1[actual_pattern = otp_pattern]", "0/1", "Exact mode sequence match"], [2000, 3500, 1000, 2500]),
                    createDataRow(["Route Jaccard", "|A ∩ O| / |A ∪ O|", "[0,1]", "Route set similarity"], [2000, 3500, 1000, 2500]),
                    createDataRow(["Stop Match", "|actual ∩ otp| / |actual|", "[0,1]", "Stop matching rate"], [2000, 3500, 1000, 2500]),
                    createDataRow(["Transfer Diff", "T_actual - T_otp", "Integer", "Transfer count difference"], [2000, 3500, 1000, 2500]),
                    createDataRow(["Time Ratio", "T_otp / T_actual", "(0,∞)", "Travel time ratio"], [2000, 3500, 1000, 2500])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 3. Similarity Metrics Definition", bold: true })] }),

            // Table 4: Similarity Statistics
            new Table({
                columnWidths: [2200, 2000, 1200, 1200, 1400],
                rows: [
                    createHeaderRow(["Metric", "Method", "Mean", "Median", "Std. Dev."], [2200, 2000, 1200, 1200, 1400]),
                    createDataRow(["Route Jaccard", "Best Jaccard", "0.593", "0.5", "0.359"], [2200, 2000, 1200, 1200, 1400]),
                    createDataRow(["Route Jaccard", "GC Optimal", "0.438", "0.5", "0.419"], [2200, 2000, 1200, 1200, 1400]),
                    createDataRow(["Modal Match", "Best Jaccard", "0.609", "1.0", "0.488"], [2200, 2000, 1200, 1200, 1400]),
                    createDataRow(["Stop Match", "Best Jaccard", "0.704", "1.0", "0.335"], [2200, 2000, 1200, 1200, 1400])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 4. Similarity Statistics (N = 886,769)", bold: true })] }),

            // Table 5: Route Jaccard Distribution
            new Table({
                columnWidths: [3000, 2500, 2500],
                rows: [
                    createHeaderRow(["Range", "Best Jaccard", "GC Optimal"], [3000, 2500, 2500]),
                    createDataRow(["Exact Match (=1.0)", "337,605 (38.1%)", "269,554 (30.4%)"], [3000, 2500, 2500]),
                    createDataRow(["Partial Match (0<x<1)", "430,868 (48.6%)", "266,127 (30.0%)"], [3000, 2500, 2500]),
                    createDataRow(["No Match (=0)", "118,296 (13.3%)", "351,088 (39.6%)"], [3000, 2500, 2500])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 5. Route Jaccard Distribution", bold: true })] }),

            // Figure 2: Jaccard Distribution
            ...createFigure(figure2Data, "Figure 1. Route Jaccard Similarity Distribution (N=886,769)", 480, 200),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Under the Best Jaccard method, 86.7% of trips show at least partial overlap with OTP alternative routes. In 71.6% of trips, the GC optimal route (idx=0) showed highest similarity to actual routes. However, 28.4% had higher similarity with 2nd-5th ranked alternatives, suggesting factors beyond cost influence route choice.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // Table 6: User Type Route Jaccard
            new Table({
                columnWidths: [1800, 1500, 1800, 1800, 1800],
                rows: [
                    createHeaderRow(["User Type", "Sample", "Route Jaccard", "Exact Match", "No Match"], [1800, 1500, 1800, 1800, 1800]),
                    createDataRow(["Children", "5,012", "0.725", "62.3%", "13.7%"], [1800, 1500, 1800, 1800, 1800]),
                    createDataRow(["Youth", "26,170", "0.663", "52.2%", "14.5%"], [1800, 1500, 1800, 1800, 1800]),
                    createDataRow(["Disabled", "25,268", "0.636", "44.7%", "13.0%"], [1800, 1500, 1800, 1800, 1800]),
                    createDataRow(["Elderly", "110,410", "0.611", "38.8%", "12.4%"], [1800, 1500, 1800, 1800, 1800]),
                    createDataRow(["General", "719,909", "0.585", "37.0%", "13.4%"], [1800, 1500, 1800, 1800, 1800]),
                    createDataRow(["Total", "886,769", "0.593", "38.1%", "13.3%"], [1800, 1500, 1800, 1800, 1800])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 6. Route Jaccard by User Type (Best Jaccard)", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Children show the highest Exact Match rate (62.3%) while general users show the lowest (37.0%). This likely reflects children using repetitive routes for school commutes while general users utilize more diverse routes. These patterns highlight limitations of the deterministic \"optimal route\" concept.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "MODEL SPECIFICATION", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "We apply a Multinomial Logit (MNL) model. The utility function for route j is: V_j = β_ride × T_ride + β_walk × T_walk + β_transfer × N_transfer + β_subway × D_subway + β_sp × D_subway × D_peak + β_tp × N_transfer × D_peak. Where T_ride is in-vehicle time (minutes), T_walk is total walking time (minutes), N_transfer is number of transfers, D_subway is subway inclusion indicator (0/1), and D_peak is peak hour indicator (0/1). Under MNL, the choice probability for route j is P(j) = exp(V_j) / Σexp(V_k). Maximum likelihood estimation (MLE) was applied using Python's Biogeme package.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "RESEARCH FRAMEWORK", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({ text: "Figure 2 illustrates the overall research workflow.", size: 24, font: "Times New Roman" })]
            }),

            // Figure 1: Research Framework
            ...createFigure(figure1Data, "Figure 2. Research Framework", 450, 380),

            // ========== 4. RESULTS ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "RESULTS", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "OVERALL MODEL ESTIMATION RESULTS", bold: true })] }),

            // Table 7: Model Fit Statistics
            new Table({
                columnWidths: [5000, 3000],
                rows: [
                    createHeaderRow(["Statistic", "Value"], [5000, 3000]),
                    createDataRow(["Observations (N)", "187,010"], [5000, 3000]),
                    createDataRow(["Log-Likelihood (Initial)", "-88,948.81"], [5000, 3000]),
                    createDataRow(["Log-Likelihood (Final)", "-83,677.69"], [5000, 3000]),
                    createDataRow(["ρ² (rho-squared)", "0.059"], [5000, 3000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 7. Model Fit Statistics", bold: true })] }),

            // Table 8: Parameter Estimates
            new Table({
                columnWidths: [2800, 1200, 1200, 1200, 1000],
                rows: [
                    createHeaderRow(["Variable", "Estimate", "Std. Error", "t-statistic", "Sig."], [2800, 1200, 1200, 1200, 1000]),
                    createDataRow(["In-vehicle Time (β_ride)", "-0.082", "0.002", "-34.7", "***"], [2800, 1200, 1200, 1200, 1000]),
                    createDataRow(["Walking Time (β_walk)", "-0.699", "0.004", "-198.4", "***"], [2800, 1200, 1200, 1200, 1000]),
                    createDataRow(["Transfer Count (β_transfer)", "-4.194", "0.029", "-145.2", "***"], [2800, 1200, 1200, 1200, 1000]),
                    createDataRow(["Subway Included (β_subway)", "+2.711", "0.028", "+95.6", "***"], [2800, 1200, 1200, 1200, 1000]),
                    createDataRow(["Peak×Subway (β_sp)", "+0.468", "0.052", "+8.9", "***"], [2800, 1200, 1200, 1200, 1000]),
                    createDataRow(["Peak×Transfer (β_tp)", "-0.287", "0.046", "-6.2", "***"], [2800, 1200, 1200, 1200, 1000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 8. MNL Parameter Estimates (Overall Model). Significance: *** p<0.001", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "All parameters are statistically significant at the 0.1% level, with signs consistent with theoretical expectations. The walking time weight (β_walk / β_ride = 8.5) indicates that users perceive 1 minute of walking as equivalent to 8.5 minutes of in-vehicle travel. This ratio exceeds previous estimates of 2–3× reported in European studies (8) and the default WALK_RELUCTANCE of 1.0 in OTP, which represents only 1/8 of the empirically observed perception.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "USER-TYPE-SPECIFIC ANALYSIS", bold: true })] }),

            // Table 9: Parameter by User Type
            new Table({
                columnWidths: [2000, 1200, 1200, 1200, 1200, 1200],
                rows: [
                    createHeaderRow(["Parameter", "General", "Youth", "Elderly", "Disabled", "Children"], [2000, 1200, 1200, 1200, 1200, 1200]),
                    createDataRow(["β_ride", "-0.084", "-0.078", "-0.070", "-0.072", "-0.043"], [2000, 1200, 1200, 1200, 1200, 1200]),
                    createDataRow(["β_walk", "-0.685", "-0.799", "-0.770", "-0.807", "-0.833"], [2000, 1200, 1200, 1200, 1200, 1200]),
                    createDataRow(["β_transfer", "-4.04", "-4.59", "-5.94", "-4.62", "-4.78"], [2000, 1200, 1200, 1200, 1200, 1200]),
                    createDataRow(["β_subway", "+2.49", "+2.95", "+4.72", "+2.93", "+2.77"], [2000, 1200, 1200, 1200, 1200, 1200]),
                    createDataRow(["Walk Weight", "8.2×", "10.3×", "11.0×", "11.2×", "19.6×"], [2000, 1200, 1200, 1200, 1200, 1200]),
                    createDataRow(["ρ²", "0.370", "0.510", "0.589", "0.524", "0.544"], [2000, 1200, 1200, 1200, 1200, 1200])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 9. Parameter Comparison by User Type", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Model fit improves substantially when estimating user-type-specific models. The pooled model achieves ρ² = 0.059, while user-type-specific models achieve ρ² = 0.370–0.589—a 6–10 fold improvement. For comparison, prior route choice studies using smart card data report ρ² values of 0.15–0.30 (9, 1). The improvement from pooled to segmented models suggests that aggregate preference assumptions mask substantial behavioral heterogeneity.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // Figure 3: Parameter Comparison
            ...createFigure(figure3Data, "Figure 3. MNL Parameter Comparison by User Type", 450, 270),

            // Table 10: Behavioral Differences
            new Table({
                columnWidths: [1800, 2000, 2000, 2000],
                rows: [
                    createHeaderRow(["User Type", "Transfer Aversion", "Subway Pref.", "Walk Weight"], [1800, 2000, 2000, 2000]),
                    createDataRow(["Youth", "+14%", "+19%", "+25%"], [1800, 2000, 2000, 2000]),
                    createDataRow(["Elderly", "+47%", "+90%", "+34%"], [1800, 2000, 2000, 2000]),
                    createDataRow(["Disabled", "+14%", "+18%", "+36%"], [1800, 2000, 2000, 2000]),
                    createDataRow(["Children", "+18%", "+11%", "+139%"], [1800, 2000, 2000, 2000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 10. Behavioral Differences Relative to General Users", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Elderly users avoid transfers 47% more than general users (β = -5.94 vs. -4.04) and prefer subway 90% more (β = +4.72 vs. +2.49). This pattern likely reflects physical constraints associated with transfers—climbing stairs, navigating crowds, and time pressure—that disproportionately affect older travelers. The walking weight for disabled users (11.2×) is 36% higher than general users (8.2×), consistent with the additional physical effort required for mobility-impaired individuals.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "MODEL VALIDATION", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Hold-out validation was performed using an 80/20 train-test split. Hit Rate is defined as the proportion of trips where the model-predicted highest-probability route matches the actually chosen route (i.e., the chosen alternative has the maximum predicted probability among all alternatives in the choice set).",
                    size: 24, font: "Times New Roman"
                })]
            }),
            new Paragraph({ children: [] }),  // Empty line between paragraphs

            // Table 11: Hold-out Validation
            new Table({
                columnWidths: [3000, 2000, 2000, 1500],
                rows: [
                    createHeaderRow(["Metric", "Train (80%)", "Test (20%)", "Diff."], [3000, 2000, 2000, 1500]),
                    createDataRow(["Mean Choice Probability", "72.34%", "72.51%", "+0.24%"], [3000, 2000, 2000, 1500]),
                    createDataRow(["Hit Rate", "75.11%", "75.69%", "+0.77%"], [3000, 2000, 2000, 1500]),
                    createDataRow(["ρ²", "0.573", "0.579", "+1.01%"], [3000, 2000, 2000, 1500])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 11. Hold-out Validation Results", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Test set performance matching training results indicates no overfitting, which we attribute to the large sample size (187,010 trips) and parsimonious model specification (6 parameters). Likelihood ratio tests comparing user-type-specific parameters yielded p < 0.001 for all pairwise comparisons, confirming that the observed behavioral differences are statistically significant and not attributable to sampling variation.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // ========== 5. SYSTEM IMPLEMENTATION ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "SYSTEM IMPLEMENTATION", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "OTP PROBABILISTIC ROUTE ASSIGNMENT MODULE", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "We developed a probabilistic route assignment module integrating the estimated MNL parameters with OTP. Core components include: MnlParameters (stores β parameters for 5 user types), RouteAttributes (extracts utility function variables from routes), RouteDeduplicator (removes duplicate routes), ProbabilityCalculator (computes MNL choice probabilities), and ProbabilisticBatchRouter (batch processing with JSON output). Max-normalization was applied during exp(V) calculation to prevent overflow, ensuring numerical stability.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "TEST RESULTS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "To validate the developed probabilistic route assignment module, we computed user-type-specific choice probabilities for various OD pairs within Seoul. Analysis examined how route choice probabilities differ by user type given identical origin-destination pairs and departure times.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading3", children: [new TextRun({ text: "Test Case 1: Myeongdong → Yeoksam (09:00)", bold: true })] }),

            // Table 12: Myeongdong→Yeoksam
            new Table({
                columnWidths: [2200, 1100, 1100, 900, 1000, 1000, 1000],
                rows: [
                    createHeaderRow(["Route", "Ride", "Walk", "Trans.", "General", "Elderly", "Children"], [2200, 1100, 1100, 900, 1000, 1000, 1000]),
                    createDataRow(["Line 4→Line 2", "29.5m", "1.8m", "1", "56.2%", "67.0%", "47.2%"], [2200, 1100, 1100, 900, 1000, 1000, 1000]),
                    createDataRow(["Bus 463 (Direct)", "35.6m", "3.7m", "0", "40.9%", "32.2%", "52.1%"], [2200, 1100, 1100, 900, 1000, 1000, 1000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 12. Probability Test Results (Myeongdong → Yeoksam)", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Despite requiring one transfer, elderly users (67.0%) select the subway route with +10.8 percentage points higher probability than general users (56.2%). Children (52.1%) prefer the direct bus route +11.2 percentage points more than general users (40.9%).",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading3", children: [new TextRun({ text: "Test Case 2: Guro Digital Complex → Jongno (10:00)", bold: true })] }),

            // Table 13: Guro→Jongno
            new Table({
                columnWidths: [2200, 1100, 1100, 900, 1000, 1000, 1000],
                rows: [
                    createHeaderRow(["Route", "Ride", "Walk", "Trans.", "General", "Elderly", "Disabled"], [2200, 1100, 1100, 900, 1000, 1000, 1000]),
                    createDataRow(["Line 2→Line 1", "29.0m", "1.9m", "1", "38.6%", "13.6%", "42.9%"], [2200, 1100, 1100, 900, 1000, 1000, 1000]),
                    createDataRow(["Line 2 Direct", "29.0m", "8.1m", "0", "31.3%", "43.9%", "29.1%"], [2200, 1100, 1100, 900, 1000, 1000, 1000]),
                    createDataRow(["Line 2 Direct (Alt)", "29.5m", "8.1m", "0", "30.1%", "42.4%", "28.0%"], [2200, 1100, 1100, 900, 1000, 1000, 1000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 13. Probability Test Results (Guro Digital Complex → Jongno)", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Elderly users select zero-transfer routes at 86.3% probability even when requiring 6.2 additional minutes of walking, while general users most prefer the 1-transfer route at 38.6%. Disabled users prefer the 1-transfer route at 42.9%, as their 11.2× walking weight makes 6 additional minutes a significant burden.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading3", children: [new TextRun({ text: "Test Case 3: Hapjeong → Seolleung (09:30)", bold: true })] }),

            // Table 14: Hapjeong→Seolleung
            new Table({
                columnWidths: [2500, 1200, 1200, 1000, 1200, 1200, 1200],
                rows: [
                    createHeaderRow(["Route", "Ride", "Walk", "Trans.", "General", "Elderly", "Diff."], [2500, 1200, 1200, 1000, 1200, 1200, 1200]),
                    createDataRow(["Line 2 (Direct)", "39.5m", "6.5m", "0", "85.9%", "97.2%", "+11.4pp"], [2500, 1200, 1200, 1000, 1200, 1200, 1200]),
                    createDataRow(["Line 6→Bus", "39.4m", "6.0m", "1", "10.1%", "2.0%", "-8.1pp"], [2500, 1200, 1200, 1000, 1200, 1200, 1200]),
                    createDataRow(["Other", "-", "-", "-", "4.0%", "0.8%", "-"], [2500, 1200, 1200, 1000, 1200, 1200, 1200])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 14. Probability Test Results (Hapjeong → Seolleung)", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "With nearly identical in-vehicle and walking times between routes, elderly users overwhelmingly prefer the transfer-free subway route at 97.2%. General users also show high preference at 85.9%, but the gap from elderly users reaches +11.4 percentage points.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading3", children: [new TextRun({ text: "Choice Probability Differences Summary", bold: true })] }),

            // Table 15: Summary
            new Table({
                columnWidths: [1800, 2200, 1000, 1000, 1000, 2000],
                rows: [
                    createHeaderRow(["OD Pair", "Route Comparison", "General", "Elderly", "Diff.", "Primary Factor"], [1800, 2200, 1000, 1000, 1000, 2000]),
                    createDataRow(["Myeongdong→Yeoksam", "Subway vs. Bus", "56.2%", "67.0%", "+10.8pp", "β_subway diff."], [1800, 2200, 1000, 1000, 1000, 2000]),
                    createDataRow(["Guro→Jongno", "0 vs. 1 Transfer", "61.4%", "86.3%", "+24.9pp", "β_transfer diff."], [1800, 2200, 1000, 1000, 1000, 2000]),
                    createDataRow(["Hapjeong→Seolleung", "0 vs. 1 Transfer", "85.9%", "97.2%", "+11.4pp", "β_transfer diff."], [1800, 2200, 1000, 1000, 1000, 2000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 15. Choice Probability Differences Summary by User Type", bold: true })] }),

            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Route choice probabilities differ by up to 25 percentage points between user types for identical OD pairs. Current systems recommending a single \"optimal route\" to all users do not reflect this heterogeneity.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // ========== 6. CONCLUSIONS ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "CONCLUSIONS", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "RESEARCH CONTRIBUTIONS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "This study quantified user-type-specific heterogeneity in transit route choice behavior using 187,010 trips from Seoul's smart card data and developed a probabilistic route assignment system. Key findings include: (1) 1 minute of walking equals 8.5 minutes of in-vehicle time in perceived burden; (2) Elderly users avoid transfers 47% more and prefer subway 90% more; (3) Disabled users' walking weight is 36% higher than general users; (4) Hold-out validation confirmed no overfitting; (5) Successful development of OTP-integrated module.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "POLICY IMPLICATIONS", bold: true })] }),

            // Table 16: Policy Recommendations
            new Table({
                columnWidths: [2000, 2500, 4000],
                rows: [
                    createHeaderRow(["User Type", "Key Characteristics", "Policy Recommendations"], [2000, 2500, 4000]),
                    createDataRow(["Elderly", "Transfer aversion, Subway pref.", "Expand direct routes, Improve subway station access"], [2000, 2500, 4000]),
                    createDataRow(["Disabled", "High walking burden", "Expand low-floor buses, Improve sidewalks, Install elevators"], [2000, 2500, 4000]),
                    createDataRow(["Overall", "High walking weight", "Improve stop accessibility, Optimize stop spacing"], [2000, 2500, 4000])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 16. Policy Recommendations by User Type", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "OTP PARAMETER RECOMMENDATIONS", bold: true })] }),

            // Table 17: OTP Parameters
            new Table({
                columnWidths: [3500, 2500, 2500],
                rows: [
                    createHeaderRow(["Parameter", "Current Default", "Recommended"], [3500, 2500, 2500]),
                    createDataRow(["WALK_RELUCTANCE", "1.0", "8.0~9.0"], [3500, 2500, 2500]),
                    createDataRow(["TRANSFER_COST", "120 sec", "Increase"], [3500, 2500, 2500])
                ]
            }),
            new Paragraph({ style: "TableCaption", children: [new TextRun({ text: "Table 17. Recommended OTP Parameters", bold: true })] }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "LIMITATIONS AND FUTURE RESEARCH", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Study limitations include: single-day data not capturing day-of-week or seasonal effects; use of exact matches only, analyzing only 38% of total trips; omission of additional variables such as fares, crowding, and weather. Future research directions include: Mixed Logit models to analyze within-individual heterogeneity; real-time API service development; generalization validation through application to other cities.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            new Paragraph({ style: "Heading2", children: [new TextRun({ text: "CONCLUDING REMARKS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({
                    text: "Returning to the motivating question—do transit users maximize utility or follow algorithms?—the evidence suggests they do maximize utility, but with heterogeneous preference structures that current algorithms fail to capture. For elderly users, transfer aversion and subway preference differ substantially from general users. Routing systems that assume uniform preferences will systematically mispredict behavior for these groups. The user-type-specific probabilistic route assignment framework developed here provides both a theoretical contribution to understanding preference heterogeneity and a practical tool for implementing personalized transit services.",
                    size: 24, font: "Times New Roman"
                })]
            }),

            // ========== ACKNOWLEDGEMENTS ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "ACKNOWLEDGEMENTS", bold: true })] }),
            new Paragraph({
                style: "Normal",
                children: [new TextRun({ text: "[Acknowledgements - To be added]", size: 24, font: "Times New Roman" })]
            }),

            // ========== REFERENCES ==========
            new Paragraph({ style: "Heading1", children: [new TextRun({ text: "REFERENCES", bold: true })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Arriagada, J., Guevara, C. A., Munizaga, M., et al., \"An experiential learning-based transit route choice model using large-scale smart-card data\", Transportation, 52, 2025, pp. 1543-1568", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Ben-Akiva, M., and Lerman, S. R., Discrete Choice Analysis: Theory and Application to Travel Demand, MIT Press, 1985", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Böcker, L., Amen, P., and Helbich, M., \"Elderly travel frequencies and transport mode choices in Greater Rotterdam\", Transportation, 44(4), 2017, pp. 831-852", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Chen, Y., et al., \"How does preference heterogeneity affect elderly's evaluation of bus accessibility?\", Journal of Transport & Health, 21, 2021, 101052", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Delling, D., Pajor, T., and Werneck, R. F., \"Round-based public transit routing\", Transportation Science, 49(3), 2015, pp. 591-604", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Dixit, M., Cats, O., van Oort, N., et al., \"Validation of a multi-modal transit route choice model using smartcard data\", Transportation, 51, 2024, pp. 1809-1829", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Garcia-Martinez, A., Cascajo, R., Jara-Diaz, S. R., et al., \"Transfer penalties in multimodal public transport networks\", Transportation Research Part A, 109, 2018, pp. 52-66", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Jara-Diaz, S., et al., \"An international time equivalency of the pure transfer penalty\", Transport Policy, 125, 2022, pp. 48-55", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Kim, I., Kim, H., Seo, D., and Kim, J. I., \"Calibration of a transit route choice model using revealed population data of smartcard in Seoul\", Transportation, 2019", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Prato, C. G., \"Route choice modeling: Past, present and future research directions\", Journal of Choice Modelling, 2(1), 2009, pp. 65-100", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Tomhave, B. J., and Khani, A., \"Refined choice set generation and the investigation of multi-criteria transit route choice behavior\", Transportation Research Part A, 154, 2021, pp. 263-282", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Train, K. E., Discrete Choice Methods with Simulation (2nd ed.), Cambridge University Press, 2009", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Wang, J., et al., \"Understanding heterogeneous passenger route choice with express and local trains\", Urban Rail Transit, 2024", size: 22, font: "Times New Roman" })] }),
            new Paragraph({ numbering: { reference: "ref-list", level: 0 }, children: [new TextRun({ text: "Yoo, G. S., \"Transfer penalty estimation with transit trips from smartcard data in Seoul, Korea\", KSCE Journal of Civil Engineering, 19, 2015, pp. 1108-1116", size: 22, font: "Times New Roman" })] })
        ]
    }]
});

// Save the document
const outputPath = "/Users/kimtaewoo/Documents/연구/main_project/최적경로 일치여부/probabilistic-otp/docs/PAPER_ENG_DRAFT.docx";

Packer.toBuffer(doc).then(buffer => {
    fs.writeFileSync(outputPath, buffer);
    console.log("English paper generated:", outputPath);
}).catch(err => {
    console.error("Error:", err);
});
