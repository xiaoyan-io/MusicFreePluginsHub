;(async () => {
  const API_BASE = "https://music-api.gdstudio.xyz/api.php"
  const SOURCE = "netease"
  const SEARCH_KEYWORD = "周杰伦"
  const QUALITY = 320

  const buildUrl = (params) => {
    const query = new URLSearchParams(params)
    return `${API_BASE}?${query.toString()}`
  }

  const search = async () => {
    const url = buildUrl({
      types: "search",
      source: SOURCE,
      name: SEARCH_KEYWORD,
      count: 5,
      pages: 1,
    })
    const resp = await fetch(url)
    if (!resp.ok) throw new Error("search failed")
    const data = await resp.json()
    return (data.data && data.data[0]) || null
  }

  const fetchUrl = async (trackId) => {
    const url = buildUrl({
      types: "url",
      source: SOURCE,
      id: trackId,
      br: QUALITY,
    })
    const resp = await fetch(url)
    if (!resp.ok) throw new Error("url fetch failed")
    const data = await resp.json()
    return data.url
  }

  try {
    const track = await search()
    if (!track) return
    const audioUrl = await fetchUrl(track.id)
    window.GDStudioAutoNext = {
      title: track.name,
      artist: track.artist?.join("、") || "",
      source: SOURCE,
      mp3: audioUrl,
      autoNext: true,
    }
    console.debug("GD Studio AutoNext ready", window.GDStudioAutoNext)
  } catch (error) {
    console.error("GD Studio AutoNext failed", error)
  }
})()
