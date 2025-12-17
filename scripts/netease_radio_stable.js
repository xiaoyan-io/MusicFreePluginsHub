const axios = require("axios");
const CryptoJS = require("crypto-js");
const qs = require("qs");
const bigInt = require("big-integer");
const dayjs = require("dayjs");

const headers = {
  authority: "music.163.com",
  "user-agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
  "content-type": "application/x-www-form-urlencoded",
  accept: "*/*",
  origin: "https://music.163.com",
  referer: "https://music.163.com",
};

const pageSize = 30;

function random16() {
  const s = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let r = "";
  for (let i = 0; i < 16; i++) r += s[Math.floor(Math.random() * s.length)];
  return r;
}

function aesEncrypt(text, key) {
  return CryptoJS.AES.encrypt(
    CryptoJS.enc.Utf8.parse(text),
    CryptoJS.enc.Utf8.parse(key),
    {
      iv: CryptoJS.enc.Utf8.parse("0102030405060708"),
      mode: CryptoJS.mode.CBC,
    }
  ).toString();
}

function rsaEncrypt(text) {
  const e = "010001";
  const n =
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7";
  const reversed = text.split("").reverse().join("");
  const hex = Buffer.from(reversed).toString("hex");
  const res = bigInt(hex, 16).modPow(bigInt(e, 16), bigInt(n, 16)).toString(16);
  return res.padStart(256, "0");
}

function getParams(data) {
  const text = JSON.stringify(data);
  const secKey = random16();
  const encText = aesEncrypt(aesEncrypt(text, "0CoJUm6Qyw8W8jud"), secKey);
  return {
    params: encText,
    encSecKey: rsaEncrypt(secKey),
  };
}

async function post(url, data, retry = 2) {
  try {
    return (
      await axios.post(url, qs.stringify(data), {
        headers,
        timeout: 8000,
      })
    ).data;
  } catch (e) {
    if (retry > 0) {
      await new Promise((r) => setTimeout(r, 500));
      return post(url, data, retry - 1);
    }
    throw e;
  }
}

function formatMusicItem(p) {
  const s = p?.mainSong || {};
  return {
    id: s.id,
    title: s.name || "",
    artist: s.artists?.[0]?.name || "",
    album: p?.radio?.name || "",
    artwork: p?.coverUrl || "",
    url: s.id
      ? `https://music.163.com/song/media/outer/url?id=${s.id}.mp3`
      : "",
    qualities: { standard: { size: s?.lMusic?.size } },
  };
}

function formatAlbumItem(p) {
  return {
    id: p.id,
    title: p.name,
    artist: p.dj?.nickname || "",
    artwork: p.picUrl,
    description: p.desc,
    date: dayjs(p.createTime).format("YYYY-MM-DD"),
  };
}

async function searchAlbum(query, page) {
  const data = getParams({
    s: query,
    type: 1009,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });
  const res = await post("https://music.163.com/weapi/search/get", data);
  const list = res?.result?.djRadios || [];
  return {
    isEnd: list.length < pageSize,
    data: list.map(formatAlbumItem),
  };
}

async function getAlbumInfo(album, page) {
  const data = getParams({
    radioId: album.id,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });
  const res = await post(
    "https://music.163.com/weapi/dj/program/byradio",
    data
  );
  const programs = res?.programs || [];
  return {
    isEnd: programs.length < pageSize,
    musicList: programs.map(formatMusicItem),
  };
}

module.exports = {
  platform: "网易云电台(稳定版)",
  version: "1.0.0",
  supportedSearchType: ["album"],
  search: (q, p) => searchAlbum(q, p),
  getAlbumInfo,
  getMediaSource: (item) => ({ url: item.url }),
};
