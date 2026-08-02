import Meting from '@meting/core';

const action = process.argv[2]; // 'search' or 'url'
const keyword = process.argv[3] || '';
const songId = process.argv[3] || '';

async function main() {
  if (action === 'search' && keyword) {
    const meting = new Meting('netease');
    meting.format(true);
    const result = await meting.search(keyword, { page: 1, limit: 10 });
    const songs = JSON.parse(result);
    // Output normalized JSON
    const output = songs.map((s, i) => ({
      index: i + 1,
      id: s.id || '',
      name: s.name || '未知',
      artist: Array.isArray(s.artist) ? s.artist.join(', ') : (s.artist || '未知'),
      album: s.album || '',
      duration: s.duration || 0,
      cover: s.pic_id || s.cover || '',
    }));
    process.stdout.write(JSON.stringify(output));
  } else if (action === 'url' && songId) {
    const meting = new Meting('netease');
    meting.format(true);
    const result = await meting.url(songId);
    const data = typeof result === 'string' ? JSON.parse(result) : result;
    process.stdout.write(JSON.stringify({
      url: data.url || '',
      size: data.size || 0,
      br: data.br || 0,
    }));
  } else {
    process.stdout.write(JSON.stringify({ error: 'usage: netease_search.mjs search <keyword> | url <song_id>' }));
  }
}

main().catch(e => {
  process.stdout.write(JSON.stringify({ error: e.message }));
});