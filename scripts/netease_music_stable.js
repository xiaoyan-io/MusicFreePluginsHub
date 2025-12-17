const axios = require("axios");
const CryptoJS = require("crypto-js");

const pageSize = 30;

function md5(t) {
  return CryptoJS.MD5(t).toString();
}

function aes(t) {
  return CryptoJS.AES.encrypt(
    CryptoJS.enc.Utf8.parse(t),
    CryptoJS.enc.Utf8.parse("e82ckenh8dichen8"),
    { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 }
  )
    .ciphertext.toString()
    .toUpperCase();
}

async function eapi(path, data = {}) {
  const text =
    path +
    "-36cd479b6b5-" +
    JSON.stringify(data) +
    "-36cd479b6b5-" +
    md5("nobody" + path + JSON.stringify(data) + "md5forencrypt");
  const params = aes(text);
  return (
    await axios.post(
      "https://interface3.music.163.com/e" + path,
      "params=" + params,
      {
        timeout: 8000,
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
      }
    )
  ).data;
}

async function getMediaSource(item, quality = "standard") {
  const levelMap = {
    low: "standard",
    standard: "exhigh",
    high: "lossless",
  };
  const res = await eapi("/api/song/enhance/player/url/v1", {
    ids: [item.id],
    level: levelMap[quality] || "standard",
  });
  const d = res?.data?.[0];
  if (d?.url) {
    return { url: d.url.split("?")[0], size: d.size };
  }
  return {
    url: `https://music.163.com/song/media/outer/url?id=${item.id}.mp3`,
  };
}

async function search(query, page) {
  const res = await eapi("/api/search/get", {
    s: query,
    type: 1,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });
  const songs = res?.result?.songs || [];
  return {
    isEnd: songs.length < pageSize,
    data: songs.map((s) => ({
      id: s.id,
      title: s.name,
      artist: s.artists.map((a) => a.name).join("/"),
      album: s.album?.name,
      artwork: s.album?.picUrl,
      qualities: { standard: {} },
    })),
  };
}

module.exports = {
  platform: "网易云音乐(稳定版)",
  version: "1.0.0",
  supportedSearchType: ["music"],
  search,
  getMediaSource,
};
