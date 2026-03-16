// =============================================
// Dexie.js Local Database for UI Navigator Agent
// =============================================

const db = new Dexie("UIAgentDrive");

// Schema: 3 tables
db.version(1).stores({
    profile: "key, category",           // Personal info key-value pairs
    documents: "++id, name, type, dateAdded", // PDFs, resumes, certificates
    images: "++id, name, dateAdded"          // Photos, ID scans, signatures
});


// =============================================
// PROFILE DATA (Key-Value Personal Info)
// =============================================

const PROFILE_CATEGORIES = [
    "personal",   // name, DOB, gender, nationality
    "contact",    // email, phone, address
    "education",  // degree, university, GPA, graduation year
    "work",       // company, job title, experience
    "financial",  // bank name, account number
    "medical",    // blood type, allergies
    "social",     // LinkedIn, GitHub, Twitter
    "other"       // anything else
];

// Common field suggestions per category
const FIELD_SUGGESTIONS = {
    personal: ["Full Name", "First Name", "Last Name", "Date of Birth", "Gender", "Nationality", "Father's Name", "Mother's Name", "Marital Status", "Religion"],
    contact: ["Email", "Phone Number", "Mobile", "Address", "City", "State", "Country", "ZIP Code", "Alternate Email", "Alternate Phone"],
    education: ["Degree", "University", "College", "Major", "GPA", "CGPA", "Graduation Year", "Board", "School Name", "Roll Number", "Registration Number"],
    work: ["Company", "Job Title", "Department", "Work Experience (Years)", "Salary", "Employee ID", "Skills"],
    financial: ["Bank Name", "Account Number", "IFSC Code", "PAN Number", "Aadhar Number", "SSN", "Tax ID"],
    medical: ["Blood Type", "Allergies", "Medical Conditions", "Emergency Contact", "Emergency Phone"],
    social: ["LinkedIn URL", "GitHub URL", "Twitter Handle", "Website", "Portfolio URL"],
    other: []
};


async function addProfileEntry(key, value, category = "other") {
    return await db.profile.put({ key, value, category });
}

async function getProfileEntry(key) {
    return await db.profile.get(key);
}

async function getAllProfile() {
    return await db.profile.toArray();
}

async function getProfileByCategory(category) {
    return await db.profile.where("category").equals(category).toArray();
}

async function deleteProfileEntry(key) {
    return await db.profile.delete(key);
}

async function updateProfileEntry(key, value, category) {
    return await db.profile.put({ key, value, category });
}

async function searchProfile(query) {
    const all = await db.profile.toArray();
    const q = query.toLowerCase();
    return all.filter(item =>
        item.key.toLowerCase().includes(q) ||
        item.value.toLowerCase().includes(q)
    );
}

// Get all profile data as a simple key:value object for the agent
async function getProfileAsObject() {
    const all = await db.profile.toArray();
    const result = {};
    for (const item of all) {
        result[item.key] = item.value;
    }
    return result;
}

// Get profile data as categorized object for better agent context
async function getProfileCategorized() {
    const all = await db.profile.toArray();
    const result = {};
    for (const item of all) {
        if (!result[item.category]) {
            result[item.category] = {};
        }
        result[item.category][item.key] = item.value;
    }
    return result;
}

// Get profile count
async function getProfileCount() {
    return await db.profile.count();
}


// =============================================
// DOCUMENTS (PDFs, Resumes, Certificates)
// =============================================

async function addDocument(name, type, content, mimeType) {
    return await db.documents.add({
        name,
        type,       // "resume", "certificate", "id_card", "other"
        content,    // base64 encoded
        mimeType,   // "application/pdf", etc.
        dateAdded: new Date().toISOString()
    });
}

async function getAllDocuments() {
    return await db.documents.toArray();
}

async function getDocumentById(id) {
    return await db.documents.get(id);
}

async function deleteDocument(id) {
    return await db.documents.delete(id);
}

async function getDocumentsMeta() {
    // Return metadata only (without content blob for performance)
    const docs = await db.documents.toArray();
    return docs.map(d => ({
        id: d.id,
        name: d.name,
        type: d.type,
        mimeType: d.mimeType,
        dateAdded: d.dateAdded
    }));
}


// =============================================
// IMAGES (Photos, ID Scans, Signatures)
// =============================================

async function addImage(name, content, mimeType) {
    return await db.images.add({
        name,
        content,    // base64 encoded
        mimeType,   // "image/png", "image/jpeg", etc.
        dateAdded: new Date().toISOString()
    });
}

async function getAllImages() {
    return await db.images.toArray();
}

async function getImageById(id) {
    return await db.images.get(id);
}

async function deleteImage(id) {
    return await db.images.delete(id);
}

async function getImagesMeta() {
    const imgs = await db.images.toArray();
    return imgs.map(i => ({
        id: i.id,
        name: i.name,
        mimeType: i.mimeType,
        dateAdded: i.dateAdded
    }));
}


// =============================================
// BULK OPERATIONS & UTILITIES
// =============================================

async function exportAllData() {
    return {
        profile: await db.profile.toArray(),
        documents: await getDocumentsMeta(),
        images: await getImagesMeta()
    };
}

async function getStorageSummary() {
    const profileCount = await db.profile.count();
    const docCount = await db.documents.count();
    const imgCount = await db.images.count();
    return {
        profileCount,
        docCount,
        imgCount,
        total: profileCount + docCount + imgCount
    };
}

async function clearAllData() {
    await db.profile.clear();
    await db.documents.clear();
    await db.images.clear();
}

// Smart field matcher — given a question from the agent, try to find matching profile data
async function findMatchingProfileData(question) {
    const all = await db.profile.toArray();
    const q = question.toLowerCase();

    // Direct key match
    for (const item of all) {
        if (q.includes(item.key.toLowerCase())) {
            return item;
        }
    }

    // Fuzzy matching for common patterns
    const patterns = {
        "name": ["Full Name", "First Name", "Last Name", "Name"],
        "email": ["Email", "Alternate Email"],
        "phone": ["Phone Number", "Mobile", "Alternate Phone"],
        "address": ["Address", "City", "State", "Country", "ZIP Code"],
        "birth": ["Date of Birth"],
        "dob": ["Date of Birth"],
        "gender": ["Gender"],
        "father": ["Father's Name"],
        "mother": ["Mother's Name"],
        "university": ["University", "College"],
        "degree": ["Degree", "Major"],
        "company": ["Company"],
        "job": ["Job Title"],
        "linkedin": ["LinkedIn URL"],
        "github": ["GitHub URL"],
    };

    for (const [keyword, fields] of Object.entries(patterns)) {
        if (q.includes(keyword)) {
            for (const field of fields) {
                const match = all.find(item => item.key.toLowerCase() === field.toLowerCase());
                if (match) return match;
            }
        }
    }

    return null;
}
