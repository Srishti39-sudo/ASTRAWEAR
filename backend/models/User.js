import mongoose from "mongoose";

const userSchema = new mongoose.Schema({
  firebaseUID: { type: String, unique: true },
  name: String,
  email: String,

  avatarHistory: [
    {
      measurements: Object,
      description: String,
      imageUrl: String,
      createdAt: { type: Date, default: Date.now }
    }
  ],

  astroHistory: [
    {
      fullName: String,
      gender: String,
      risingSign: String,
      venusSign: String,
      styleResult: Object,
      createdAt: { type: Date, default: Date.now }
    }
  ],

  stylistHistory: [
    {
      occasion: String,
      wardrobe: String,
      styleVibe: String,
      analysis: Object,
      outfit: Object,
      createdAt: { type: Date, default: Date.now }
    }
  ]
});

export default mongoose.model("User", userSchema);
