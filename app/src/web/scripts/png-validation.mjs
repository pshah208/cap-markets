import { inflateSync } from "node:zlib";

const SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const MAX_LOGO_BYTES = 2 * 1024 * 1024;
const MAX_DIMENSION = 4096;
const MAX_DECODED_BYTES = 64 * 1024 * 1024;
const CRC_TABLE = Array.from({ length: 256 }, (_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit++) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  return value >>> 0;
});

function fail(message) {
  throw new Error(`Logo must be a valid PNG: ${message}`);
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function paeth(left, above, upperLeft) {
  const prediction = left + above - upperLeft;
  const distances = [Math.abs(prediction - left), Math.abs(prediction - above), Math.abs(prediction - upperLeft)];
  return distances[0] <= distances[1] && distances[0] <= distances[2]
    ? left : distances[1] <= distances[2] ? above : upperLeft;
}

export function validatePng(bytes) {
  if (bytes.length > MAX_LOGO_BYTES) fail("maximum file size is 2 MiB.");
  if (bytes.length < 8 || !bytes.subarray(0, 8).equals(SIGNATURE)) {
    fail("incorrect PNG signature; SVG and other formats are not supported.");
  }

  let offset = 8;
  let header;
  let paletteEntries = 0;
  let sawIdat = false;
  let endedIdat = false;
  let sawEnd = false;
  const compressedParts = [];
  while (offset < bytes.length) {
    if (bytes.length - offset < 12) fail("truncated chunk.");
    const length = bytes.readUInt32BE(offset);
    if (length > bytes.length - offset - 12) fail("invalid chunk length.");
    const type = bytes.toString("ascii", offset + 4, offset + 8);
    const typeBytes = bytes.subarray(offset + 4, offset + 8);
    if (!typeBytes.every(byte => (byte >= 65 && byte <= 90) || (byte >= 97 && byte <= 122))
        || typeBytes[2] < 65 || typeBytes[2] > 90) {
      fail("invalid chunk type.");
    }
    const data = bytes.subarray(offset + 8, offset + 8 + length);
    const checksum = bytes.readUInt32BE(offset + 8 + length);
    if (crc32(bytes.subarray(offset + 4, offset + 8 + length)) !== checksum) {
      fail(`CRC checksum mismatch in ${type}.`);
    }
    if (!header && type !== "IHDR") fail("IHDR must be the first chunk.");
    if (sawIdat && type !== "IDAT") endedIdat = true;

    if (type === "IHDR") {
      if (header || length !== 13) fail("exactly one 13-byte IHDR is required.");
      const width = data.readUInt32BE(0);
      const height = data.readUInt32BE(4);
      const depth = data[8];
      const colorType = data[9];
      const permittedDepths = {
        0: [1, 2, 4, 8, 16], 2: [8, 16], 3: [1, 2, 4, 8], 4: [8, 16], 6: [8, 16],
      };
      if (!width || !height || width > MAX_DIMENSION || height > MAX_DIMENSION) {
        fail("width and height must each be between 1 and 4096 pixels.");
      }
      if (!permittedDepths[colorType]?.includes(depth)) fail("invalid color type or bit depth.");
      if (data[10] !== 0 || data[11] !== 0 || data[12] > 1) {
        fail("unsupported compression, filter, or interlace method.");
      }
      header = { width, height, depth, colorType, interlace: data[12] };
    } else if (type === "PLTE") {
      if (paletteEntries || sawIdat || length === 0 || length > 768 || length % 3 !== 0) {
        fail("invalid or misplaced palette.");
      }
      if (header.colorType === 0 || header.colorType === 4) fail("grayscale PNG cannot have a palette.");
      paletteEntries = length / 3;
      if (header.colorType === 3 && paletteEntries > 2 ** header.depth) fail("palette exceeds bit depth.");
    } else if (type === "IDAT") {
      if (endedIdat) fail("IDAT chunks must be consecutive.");
      if (header.colorType === 3 && !paletteEntries) fail("indexed PNG requires a palette before IDAT.");
      sawIdat = true;
      compressedParts.push(data);
    } else if (type === "IEND") {
      if (length !== 0 || !sawIdat) fail("IEND must be empty and follow image data.");
      if (offset + 12 !== bytes.length) fail("trailing data after IEND.");
      sawEnd = true;
    } else if ((typeBytes[0] & 32) === 0) {
      fail(`unsupported critical chunk ${type}.`);
    }
    offset += length + 12;
  }
  if (!header || !sawIdat || !sawEnd) fail("IHDR, IDAT and IEND chunks are required.");

  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[header.colorType];
  const passes = header.interlace
    ? [[0, 0, 8, 8], [4, 0, 8, 8], [0, 4, 4, 8], [2, 0, 4, 4],
      [0, 2, 2, 4], [1, 0, 2, 2], [0, 1, 1, 2]]
    : [[0, 0, 1, 1]];
  const rows = passes.map(([x, y, dx, dy]) => {
    const width = Math.max(0, Math.ceil((header.width - x) / dx));
    const height = Math.max(0, Math.ceil((header.height - y) / dy));
    return { width, height: width ? height : 0, size: Math.ceil(width * channels * header.depth / 8) + 1 };
  });
  const expectedBytes = rows.reduce((total, row) => total + row.height * row.size, 0);
  if (expectedBytes > MAX_DECODED_BYTES) fail("decoded image exceeds 64 MiB.");

  let decoded;
  const compressed = Buffer.concat(compressedParts);
  try {
    const result = inflateSync(compressed, { maxOutputLength: expectedBytes, info: true });
    if (result.engine.bytesWritten !== compressed.length) fail("trailing compressed image data.");
    decoded = result.buffer;
  } catch {
    fail("invalid or excessive compressed image data.");
  }
  if (decoded.length !== expectedBytes) fail("image data does not match the declared dimensions.");
  let rowOffset = 0;
  for (const { width, height, size } of rows) {
    let previous = Buffer.alloc(size - 1);
    for (let row = 0; row < height; row++) {
      const filter = decoded[rowOffset];
      if (filter > 4) fail("invalid scanline filter.");
      if (header.colorType === 3) {
        // Indexed PNGs need unfiltering before palette references can be checked.
        const current = Buffer.from(decoded.subarray(rowOffset + 1, rowOffset + size));
        for (let index = 0; index < current.length; index++) {
          const left = index ? current[index - 1] : 0;
          const above = previous[index];
          const upperLeft = index ? previous[index - 1] : 0;
          const prediction = [0, left, above, Math.floor((left + above) / 2), paeth(left, above, upperLeft)][filter];
          current[index] = (current[index] + prediction) & 255;
        }
        for (let pixel = 0; pixel < width; pixel++) {
          const bit = pixel * header.depth;
          const index = (current[Math.floor(bit / 8)] >>> (8 - header.depth - bit % 8)) & ((1 << header.depth) - 1);
          if (index >= paletteEntries) fail("pixel references a nonexistent palette entry.");
        }
        previous = current;
      }
      rowOffset += size;
    }
  }
}
