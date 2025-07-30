export default {
  preset: 'ts-jest/presets/default-esm',
  testEnvironment: 'node',
  extensionsToTreatAsEsm: ['.ts'],
  moduleNameMapper: {
    '^(\\.{1,2}/.*)\\.js$': '$1',
  },
  transform: {},
  globals: {
    'ts-jest': {
      tsconfig: {
        target: 'es2017',
        module: 'esnext',
        moduleResolution: 'node',
        esModuleInterop: true,
      },
    },
  },
};
