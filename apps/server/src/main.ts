import 'dotenv/config';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Allow requests from the bot running locally or on same network
  app.enableCors({ origin: '*' });

  // Global API prefix — /api/health, /api/bot/...
  app.setGlobalPrefix('api');

  const port = process.env.PORT ?? 3005;
  await app.listen(port, '0.0.0.0');
  console.log(`🚀 Telecode Server running on http://localhost:${port}/api`);
}
bootstrap();
